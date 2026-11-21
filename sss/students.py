import hmac
import json
import secrets
import sqlite3
from hashlib import scrypt

from flask import abort, flash, g, redirect, render_template, request, session, url_for

from .catalog import MANILA
from .db import db, timestamp, write_transaction


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32).hex()
    return salt, digest


def verify_password(account, password):
    _, digest = password_hash(password[:200], account["salt"])
    return hmac.compare_digest(digest, account["digest"])


def student(identity):
    row = db().execute("SELECT * FROM students WHERE id = ? COLLATE NOCASE", (identity or "",)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["role"] = "student"
    result["name"] = " ".join(filter(None, (result["first_name"], result["middle_name"], result["last_name"])))
    result["course"] = f'{result["program"]} {result["year_level"]}-{result["section"]}'
    return result


def fields(form):
    names = ("first_name", "middle_name", "last_name", "program", "year_level", "section", "college")
    result = {name: form.get(name, "").strip() for name in names}
    errors = []
    for name in names:
        if name != "middle_name" and not result[name]:
            errors.append(f'Enter {name.replace("_", " ")}.')
        if len(result[name]) > 100:
            errors.append(f'{name.replace("_", " ").capitalize()} must be 100 characters or less.')
    return result, errors


def register_students(app, login_required):
    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if g.user:
            return redirect(url_for("home"))
        errors = []
        if request.method == "POST":
            data, errors = fields(request.form)
            password = request.form.get("password", "")
            if not 8 <= len(password) <= 200:
                errors.append("Choose a password between 8 and 200 characters.")
            if password != request.form.get("confirm_password", ""):
                errors.append("Passwords must match.")
            if not errors:
                salt, digest = password_hash(password)
                with write_transaction() as connection:
                    from datetime import datetime
                    year = datetime.now(MANILA).year
                    for _ in range(1000):
                        identity = f'{year}-{secrets.randbelow(10000):04d}-{secrets.choice("AUI")}'
                        try:
                            connection.execute(
                                """INSERT INTO students
                                   (id, first_name, middle_name, last_name, program, year_level, section, college,
                                    salt, digest, revision, active, is_demo)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)""",
                                (identity, *data.values(), salt, digest, secrets.token_hex(16)),
                            )
                            break
                        except sqlite3.IntegrityError:
                            continue
                    else:
                        raise RuntimeError("Could not allocate a student ID.")
                flash(f"Account created. Your student ID is {identity}. Sign in to continue.")
                return redirect(url_for("login", identity=identity), 303)
        return render_template("student_form.html", mode="signup", data=request.form, errors=errors), 422 if errors else 200

    @app.route("/account/password", methods=["GET", "POST"])
    @login_required("student")
    def change_password():
        errors = []
        if request.method == "POST":
            account = student(g.user["id"])
            password = request.form.get("password", "")
            if not verify_password(account, request.form.get("current_password", "")):
                errors.append("Current password is incorrect.")
            if not 8 <= len(password) <= 200:
                errors.append("Choose a password between 8 and 200 characters.")
            if password != request.form.get("confirm_password", ""):
                errors.append("Passwords must match.")
            if not errors:
                salt, digest = password_hash(password)
                revision = secrets.token_hex(16)
                db().execute("UPDATE students SET salt=?, digest=?, revision=? WHERE id=?",
                             (salt, digest, revision, account["id"]))
                session["revision"] = revision
                flash("Password updated.")
                return redirect(url_for("home"), 303)
        return render_template("student_form.html", mode="password", errors=errors), 422 if errors else 200

    @app.get("/admin/students")
    @login_required("admin")
    def student_list():
        rows = db().execute("SELECT id FROM students ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE").fetchall()
        return render_template("students.html", students=[student(row["id"]) for row in rows])

    @app.route("/admin/students/<identity>/edit", methods=["GET", "POST"])
    @login_required("admin")
    def student_edit(identity):
        account = student(identity)
        if not account:
            abort(404)
        errors = []
        data = account
        if request.method == "POST":
            data, errors = fields(request.form)
            if not errors:
                db().execute("""UPDATE students SET first_name=?, middle_name=?, last_name=?, program=?,
                             year_level=?, section=?, college=? WHERE id=?""", (*data.values(), account["id"]))
                flash("Student details updated.")
                return redirect(url_for("student_edit", identity=account["id"]), 303)
        return render_template("student_form.html", mode="edit", data=data, account=account, errors=errors), 422 if errors else 200

    @app.post("/admin/students/<identity>/<action>")
    @login_required("admin")
    def student_action(identity, action):
        with write_transaction() as connection:
            account = student(identity)
            if not account:
                abort(404)
            if action == "reset-password":
                salt, digest = password_hash(account["last_name"])
                connection.execute("UPDATE students SET salt=?, digest=?, revision=? WHERE id=?",
                                   (salt, digest, secrets.token_hex(16), account["id"]))
                flash("Password reset to the student's surname.")
            elif action == "deactivate":
                connection.execute("UPDATE students SET active=0, revision=? WHERE id=?",
                                   (secrets.token_hex(16), account["id"]))
                flash("Student account deactivated.")
            elif action == "delete":
                if account["active"] or request.form.get("confirm_id", "") != account["id"]:
                    flash("Enter the exact student ID for a deactivated account.")
                    return redirect(url_for("student_edit", identity=account["id"]), 303)
                for table in ("issued_files", "attachments", "payment_links", "order_items"):
                    connection.execute(f"DELETE FROM {table} WHERE order_id IN (SELECT id FROM orders WHERE student_id=?)",
                                       (account["id"],))
                connection.execute("DELETE FROM orders WHERE student_id=?", (account["id"],))
                connection.execute("DELETE FROM students WHERE id=?", (account["id"],))
                flash("Student and associated records deleted.")
                return redirect(url_for("student_list"), 303)
            else:
                abort(404)
        return redirect(url_for("student_edit", identity=account["id"]), 303)
