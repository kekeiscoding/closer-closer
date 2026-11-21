import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from flask import current_app, g

from .catalog import MANILA, OSAS, REGISTRAR, UNIT_PRICE, check_academic_dates
from .pdfs import make_pdf


SCHEMA = """
CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS students (
    id TEXT PRIMARY KEY COLLATE NOCASE, first_name TEXT NOT NULL, middle_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL, program TEXT NOT NULL, year_level TEXT NOT NULL, section TEXT NOT NULL,
    college TEXT NOT NULL, salt TEXT NOT NULL, digest TEXT NOT NULL, revision TEXT NOT NULL,
    active INTEGER NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0, transcript TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    office TEXT NOT NULL CHECK (office IN ('Registrar', 'OSAS')),
    created_at TEXT NOT NULL,
    profile TEXT NOT NULL,
    answers TEXT NOT NULL,
    total INTEGER NOT NULL CHECK (total > 0),
    request_key TEXT NOT NULL,
    paid_at TEXT,
    paid_by TEXT,
    payment_method TEXT CHECK (payment_method IN ('online', 'in-person')),
    receipt TEXT UNIQUE,
    UNIQUE (student_id, request_key)
);
CREATE TABLE IF NOT EXISTS order_items (
    order_id TEXT NOT NULL REFERENCES orders(id),
    service TEXT NOT NULL,
    title TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, service)
);
CREATE TABLE IF NOT EXISTS attachments (
    order_id TEXT PRIMARY KEY REFERENCES orders(id),
    mimetype TEXT NOT NULL,
    content BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_links (
    order_id TEXT PRIMARY KEY REFERENCES orders(id),
    token TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS issued_files (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(id),
    service TEXT NOT NULL,
    title TEXT NOT NULL,
    copy INTEGER NOT NULL CHECK (copy > 0),
    verifiable INTEGER NOT NULL CHECK (verifiable IN (0, 1)),
    content BLOB NOT NULL,
    UNIQUE (order_id, service, copy),
    FOREIGN KEY (order_id, service) REFERENCES order_items(order_id, service)
);
CREATE INDEX IF NOT EXISTS student_orders ON orders(student_id, created_at DESC);
"""


def db():
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE"], timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_error):
    connection = g.pop("db", None)
    if connection:
        connection.close()


def init_db():
    connection = db()
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)
    with write_transaction() as connection:
        if not connection.execute("SELECT 1 FROM migrations WHERE name='students-v1'").fetchone():
            for account in current_app.config["ACCOUNTS"].values():
                if account["role"] != "student":
                    continue
                program, year_section = account["course"].rsplit(" ", 1)
                year_level, section = year_section.split("-", 1)
                connection.execute(
                    """INSERT INTO students
                       (id, first_name, middle_name, last_name, program, year_level, section, college,
                        salt, digest, revision, active, is_demo)
                       VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)""",
                    (account["id"], account["first_name"], account["last_name"], program, year_level,
                     section, account["college"], account["salt"], account["digest"], secrets.token_hex(16)),
                )
            connection.execute("INSERT INTO migrations VALUES ('students-v1')")


@contextmanager
def write_transaction():
    connection = db()
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


def timestamp():
    return datetime.now(MANILA).isoformat(timespec="seconds")


def identifier(prefix, size=8):
    return f"{prefix}-{secrets.token_hex(size).upper()}"


def create_order(user, office, items, answers, attachment, request_key):
    profile = {key: user[key] for key in ("id", "name", "first_name", "last_name", "course", "college")}
    order_id = identifier("IS", 6)
    total = sum(quantity for _, _, quantity in items) * UNIT_PRICE
    with write_transaction() as connection:
        existing = connection.execute(
            "SELECT id FROM orders WHERE student_id = ? AND request_key = ?", (user["id"], request_key),
        ).fetchone()
        if existing:
            return existing["id"]
        connection.execute(
            """INSERT INTO orders (id, student_id, office, created_at, profile, answers, total, request_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, user["id"], office, timestamp(), json.dumps(profile), json.dumps(answers), total, request_key),
        )
        connection.executemany(
            "INSERT INTO order_items (order_id, service, title, quantity) VALUES (?, ?, ?, ?)",
            ((order_id, *item) for item in items),
        )
        if attachment:
            connection.execute(
                "INSERT INTO attachments (order_id, mimetype, content) VALUES (?, ?, ?)",
                (order_id, *attachment),
            )
    return order_id


def order_data(row, *, include_answers=False, include_files=False):
    order = dict(row)
    order["profile"] = json.loads(order["profile"])
    order["items"] = db().execute(
        "SELECT service, title, quantity FROM order_items WHERE order_id = ? ORDER BY rowid", (order["id"],),
    ).fetchall()
    answers = json.loads(order.pop("answers"))
    issues = {}
    if order["office"] == "Registrar":
        check_academic_dates(
            dict(answers), issues,
            any(item["service"] == "grades" for item in order["items"]),
            datetime.fromisoformat(order["created_at"]).date(),
        )
    order["academic_issues"] = list(issues.values())
    if include_answers:
        order["answers"] = answers
        order["has_attachment"] = db().execute(
            "SELECT 1 FROM attachments WHERE order_id = ?", (order["id"],),
        ).fetchone() is not None
    if include_files:
        order["files"] = db().execute(
            """SELECT id, title, copy, verifiable FROM issued_files
               WHERE order_id = ? ORDER BY rowid""", (order["id"],),
        ).fetchall()
    return order


def get_order(order_id, student_id=None, *, detail=False):
    row = db().execute(
        "SELECT * FROM orders WHERE id = ? AND (? IS NULL OR student_id = ?)",
        (order_id, student_id, student_id),
    ).fetchone()
    return order_data(row, include_answers=detail, include_files=detail) if row else None


def list_orders(student_id=None):
    rows = db().execute(
        "SELECT * FROM orders WHERE (? IS NULL OR student_id = ?) ORDER BY created_at DESC, rowid DESC",
        (student_id, student_id),
    ).fetchall()
    return [order_data(row) for row in rows]


def payment_token(order_id):
    connection = db()
    lookup = "SELECT token FROM payment_links WHERE order_id = ?"
    row = connection.execute(lookup, (order_id,)).fetchone()
    if row is None:
        connection.execute(
            "INSERT INTO payment_links (order_id, token) VALUES (?, ?) ON CONFLICT(order_id) DO NOTHING",
            (order_id, secrets.token_urlsafe(32)),
        )
        row = connection.execute(lookup, (order_id,)).fetchone()
    return row["token"]


def get_guest_order(token, *, detail=False):
    row = db().execute(
        """SELECT orders.* FROM payment_links
           JOIN orders ON orders.id = payment_links.order_id WHERE payment_links.token = ?""",
        (token,),
    ).fetchone()
    return order_data(row, include_answers=detail, include_files=detail) if row else None


def guest_payment_view(order):
    titles = REGISTRAR if order["office"] == "Registrar" else {
        code: values[0] for code, values in OSAS.items()
    }
    return {
        "id": order["id"], "total": order["total"], "paid_at": order["paid_at"],
        "blocked": bool(order["academic_issues"]) and not order["paid_at"],
        "items": [{"title": titles[item["service"]], "quantity": item["quantity"]} for item in order["items"]],
    }


def paid_order_ids(student_id=None):
    rows = db().execute(
        """SELECT id FROM orders WHERE paid_at IS NOT NULL
           AND (? IS NULL OR student_id = ?) ORDER BY id""", (student_id, student_id)
    )
    return [row["id"] for row in rows]


def guest_payment_status(token):
    row = db().execute(
        """SELECT orders.paid_at FROM payment_links
           JOIN orders ON orders.id = payment_links.order_id WHERE payment_links.token = ?""",
        (token,),
    ).fetchone()
    return {"paid": bool(row["paid_at"])} if row else None


def confirm_payment(order_id, actor, method, *, token=None):
    if token is None and actor is None:
        raise ValueError("Payment requires an account or a checkout token.")
    student_id = actor["id"] if actor is not None and method == "online" else None
    with write_transaction() as connection:
        order = get_guest_order(token, detail=True) if token else get_order(order_id, student_id, detail=True)
        if order is None:
            return None
        account = connection.execute("SELECT active FROM students WHERE id=? COLLATE NOCASE", (order["student_id"],)).fetchone()
        if not order["paid_at"] and (not account or not account["active"]):
            order["academic_issues"].append("This student account is inactive.")
        if order["paid_at"] or order["academic_issues"]:
            return order
        order_id = order["id"]
        order["receipt"] = identifier("PAY", 6)
        order["paid_at"] = timestamp()
        order["payment_method"] = method
        order["sample_program"] = None
        if not connection.execute("SELECT is_demo FROM students WHERE id=?", (order["student_id"],)).fetchone()["is_demo"]:
            order["sample_program"] = order["profile"]["course"]
        if any(item["service"] == "tor" for item in order["items"]):
            record = connection.execute("SELECT is_demo, transcript FROM students WHERE id=?", (order["student_id"],)).fetchone()
            if record and not record["is_demo"]:
                transcript = record["transcript"]
                if not transcript:
                    pool = [("IT 101", "Introduction to Computing"), ("IT 102", "Computer Programming"),
                            ("GE 101", "Understanding the Self"), ("GE 102", "Mathematics in the Modern World"),
                            ("GE 103", "The Contemporary World"), ("GE 104", "Purposive Communication"),
                            ("IT 103", "Web Development"), ("IT 104", "Data Structures")]
                    import random
                    transcript = json.dumps([(code, title, 3, secrets.choice(("1.25", "1.50", "1.75", "2.00")))
                                             for code, title in random.SystemRandom().sample(pool, 4)])
                    connection.execute("UPDATE students SET transcript=? WHERE id=?", (transcript, order["student_id"]))
                order["sample_transcript"] = json.loads(transcript)
        verifiable = order["office"] == "Registrar"
        for item in order["items"]:
            for copy in range(1, item["quantity"] + 1):
                file_id = identifier("DOC" if verifiable else "FILE")
                verify_url = f"{current_app.config['APP_BASE_URL']}/verify/{file_id}" if verifiable else None
                content = make_pdf(order, item, copy, file_id, verify_url)
                connection.execute(
                    """INSERT INTO issued_files (id, order_id, service, title, copy, verifiable, content)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (file_id, order_id, item["service"], item["title"], copy, verifiable, content),
                )
        connection.execute(
            """UPDATE orders SET paid_at = ?, paid_by = ?, payment_method = ?, receipt = ?
               WHERE id = ?""",
            (order["paid_at"], actor["id"] if actor else "guest-checkout",
             method, order["receipt"], order_id),
        )
    return get_order(order_id, student_id, detail=True)


def find_document(document_id):
    document = db().execute(
        """SELECT files.id, files.title, files.copy, orders.profile, orders.paid_at, orders.id AS order_id
           FROM issued_files AS files JOIN orders ON orders.id = files.order_id
           WHERE files.id = ? AND files.verifiable = 1 AND orders.paid_at IS NOT NULL""",
        (document_id,),
    ).fetchone()
    if document is None:
        return None
    result = dict(document)
    result["profile"] = json.loads(document["profile"])
    return result
