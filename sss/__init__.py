import hmac
import os
import re
import secrets
from datetime import datetime, timedelta
from functools import wraps
from hashlib import scrypt
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for,
)
from flask_wtf import CSRFProtect
from PIL import Image
from werkzeug.middleware.proxy_fix import ProxyFix

from .accounts import DEMO_ACCOUNTS
from .catalog import (
    CLINIC_GUIDANCE, DECLARATIONS, GRADE_FIELDS, MANILA, OSAS, OSAS_FIELDS, REGISTRAR,
    REGISTRAR_DETAILS, UNIT_PRICE, osas_submission, registrar_submission, response_groups,
)
from .db import (
    close_db, confirm_payment, create_order, db, find_document, get_guest_order, get_order,
    guest_payment_view, init_db, list_orders, payment_token,
)
from .live import register_payment_updates
from .pdfs import qr_png
from .students import register_students, student, verify_password


ORDER_ID = re.compile(r"IS-[A-F0-9]{12}")
DOCUMENT_ID = re.compile(r"DOC-[A-F0-9]{16}")
PAYMENT_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
MAX_CLEARANCE = 5 * 1024 * 1024
PROFILE_KEYS = ("id", "name", "first_name", "last_name", "course", "college", "role")


def local_secret(instance):
    path = instance / "session.key"
    if not path.exists():
        temporary = path.with_name(f".session-{uuid4().hex}")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(secrets.token_hex(32))
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        finally:
            temporary.unlink()
    return path.read_text().strip()


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    origin = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    instance = Path(os.environ.get("ISATU_DATA_DIR", app.instance_path))
    app.config.from_mapping(
        APP_BASE_URL=origin,
        DATABASE=str(instance / "isatu.sqlite3"),
        SESSION_COOKIE_NAME="isatu_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=origin.startswith("https://"),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        ACCOUNTS=DEMO_ACCOUNTS,
        SOCK_SERVER_OPTIONS={"ping_interval": 25, "max_message_size": 256},
        SECRET_KEY=os.environ.get("ISATU_SECRET_KEY"),
    )
    app.config.update(config or {})
    if not app.config["SECRET_KEY"]:
        instance.mkdir(parents=True, exist_ok=True, mode=0o700)
        app.config["SECRET_KEY"] = local_secret(instance)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.environ.get("ISATU_BEHIND_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
    CSRFProtect(app)
    app.teardown_appcontext(close_db)
    app.template_filter("money")(lambda value: f"₱{value / 100:,.2f}")
    app.template_filter("date_label")(format_date)
    app.template_filter("payment_label")(lambda value: "Online demo" if value == "online" else "In person")
    app.jinja_env.globals.update(unit_price=UNIT_PRICE, registrar=REGISTRAR)
    with app.app_context():
        init_db()
    register_views(app)
    register_students(app, login_required)
    register_payment_updates(app)
    return app


def format_date(value):
    return datetime.fromisoformat(value).strftime("%b %d, %Y") if value else ""


def next_page(candidate):
    if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
        return url_for("home")
    parts = urlsplit(candidate)
    if parts.netloc or parts.scheme or any(ord(character) < 32 for character in candidate):
        return url_for("home")
    return candidate


def login_required(role=None):
    def decorate(view):
        @wraps(view)
        def guarded(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            if role and g.user["role"] != role:
                abort(403)
            return view(*args, **kwargs)
        return guarded
    return decorate


def owns_order(order_id, *, detail=False):
    student_id = None if g.user["role"] == "admin" else g.user["id"]
    order = get_order(order_id, student_id, detail=detail)
    if order is None:
        abort(404)
    return order


def read_clearance(storage):
    if not storage or not storage.filename:
        raise ValueError("Attach a clearance PDF, JPG, or PNG.")
    data = storage.read(MAX_CLEARANCE + 1)
    if len(data) > MAX_CLEARANCE:
        raise ValueError("Choose a clearance file of 5 MB or less.")
    if data.startswith(b"%PDF-") and b"%%EOF" in data[-1024:]:
        return "application/pdf", data
    try:
        with Image.open(BytesIO(data), formats=["PNG", "JPEG"]) as image:
            kind = image.format
            image.verify()
    except (OSError, SyntaxError, Image.DecompressionBombError):
        raise ValueError("Choose a valid PDF, JPG, or PNG.") from None
    return Image.MIME[kind], data


def submission_key():
    value = request.form.get("request_key", "")
    try:
        return UUID(value).hex
    except ValueError:
        abort(400, description="Reopen the request form and submit it again.")


def register_views(app):
    @app.before_request
    def load_profile():
        key = session.get("account")
        account = student(key)
        if account:
            if not account["active"] or session.get("revision") != account["revision"]:
                session.clear()
                account = None
        else:
            candidate = app.config["ACCOUNTS"].get(key)
            account = candidate if candidate and candidate["role"] == "admin" else None
        g.user = {key: account[key] for key in PROFILE_KEYS} if account else None

    @app.after_request
    def protect_response(response):
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # The checkout form uses its CSRF session and same-origin Referer over HTTPS.
        response.headers["Referrer-Policy"] = "same-origin"
        origin = urlsplit(app.config["APP_BASE_URL"])
        websocket = f"{'wss' if origin.scheme == 'https' else 'ws'}://{origin.netloc}"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; "
            f"object-src 'none'; base-uri 'self'; form-action 'self'; connect-src 'self' {websocket}"
        )
        return response

    @app.get("/healthz")
    def health():
        db().execute("SELECT 1 FROM orders LIMIT 1").fetchone()
        return {"status": "ok"}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        destination = next_page(request.values.get("next", ""))
        if g.user:
            return redirect(destination)
        error = None
        identity = request.args.get("identity", "")[:120]
        if request.method == "POST":
            identity = request.form.get("identity", "").strip()[:120]
            password = request.form.get("password", "")[:200]
            key = identity.casefold()
            account = student(identity)
            if not account:
                candidate = app.config["ACCOUNTS"].get(key)
                account = candidate if candidate and candidate["role"] == "admin" else None
            verifier = account or next(iter(app.config["ACCOUNTS"].values()))
            valid = verify_password(verifier, password)
            if account and valid and (account["role"] == "admin" or account["active"]):
                session.clear()
                session.permanent = True
                session["account"] = key
                if account["role"] == "student":
                    session["revision"] = account["revision"]
                return redirect(destination, 303)
            error = "Check your ID and password and try again."
        return render_template("login.html", error=error, identity=identity, destination=destination), (401 if error else 200)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"), 303)

    @app.get("/")
    @login_required()
    def home():
        student = g.user["role"] == "student"
        orders = list_orders(g.user["id"] if student else None)
        return render_template("home.html", orders=orders[:4])

    @app.get("/osas")
    @login_required("student")
    def osas_index():
        return render_template("osas.html", services=OSAS)

    @app.route("/osas/<service>", methods=["GET", "POST"])
    @login_required("student")
    def osas_request(service):
        if service not in OSAS:
            abort(404)
        errors = {}
        key = uuid4().hex
        if request.method == "POST":
            key = submission_key()
            items, answers, errors = osas_submission(service, request.form)
            if not errors:
                order_id = create_order(g.user, "OSAS", items, answers, None, key)
                return redirect(url_for("student_detail", order_id=order_id, received=1), 303)
        return render_template(
            "form.html", office="OSAS", heading=OSAS[service][0], guidance=CLINIC_GUIDANCE.get(service),
            groups=OSAS_FIELDS[service], declaration=DECLARATIONS[service], errors=errors,
            raw=request.form, request_key=key,
        ), (422 if errors else 200)

    @app.route("/registrar", methods=["GET", "POST"])
    @login_required("student")
    def registrar_request():
        errors = {}
        key = uuid4().hex
        if request.method == "POST":
            key = submission_key()
            items, answers, errors = registrar_submission(request.form)
            clearance = None
            if "good-moral" in request.form.getlist("services"):
                try:
                    clearance = read_clearance(request.files.get("clearance"))
                except ValueError as error:
                    errors["clearance"] = str(error)
            if not errors:
                order_id = create_order(g.user, "Registrar", items, answers, clearance, key)
                return redirect(url_for("student_detail", order_id=order_id, received=1), 303)
        return render_template(
            "form.html", office="Registrar", heading="Request Registrar documents",
            guidance=None, groups=REGISTRAR_DETAILS, grade_fields=GRADE_FIELDS,
            declaration=DECLARATIONS["registrar"], errors=errors, raw=request.form, request_key=key,
        ), (422 if errors else 200)

    @app.get("/requests")
    @login_required("student")
    def student_requests():
        return render_template("requests.html", orders=list_orders(g.user["id"]), admin=False)

    def detail_page(order, *, admin=False):
        groups = response_groups(order["office"], order["items"], order["answers"])
        checkout_url = None
        if not admin and not order["paid_at"] and not order["academic_issues"]:
            checkout_url = url_for("guest_checkout", token=payment_token(order["id"]))
        return render_template("order.html", order=order, groups=groups, admin=admin,
                               checkout_url=checkout_url,
                               received=not admin and request.args.get("received") == "1")

    @app.get("/requests/<order_id>")
    @login_required("student")
    def student_detail(order_id):
        return detail_page(owns_order(order_id, detail=True))

    @app.get("/admin/requests")
    @login_required("admin")
    def admin_requests():
        return render_template("requests.html", orders=list_orders(), admin=True)

    @app.get("/admin/requests/<order_id>")
    @login_required("admin")
    def admin_detail(order_id):
        return detail_page(owns_order(order_id, detail=True), admin=True)

    def cashier_page(admin, *, value=None):
        value = (value or request.args.get("order_id", "")).strip().upper()[:32]
        student_id = None if admin else g.user["id"]
        order = get_order(value, student_id, detail=True) if ORDER_ID.fullmatch(value) else None
        checkout_url = None
        if order and not admin and not order["paid_at"] and not order["academic_issues"]:
            checkout_url = url_for("guest_checkout", token=payment_token(order["id"]))
        return render_template("cashier.html", value=value, order=order, admin=admin,
                               checkout_url=checkout_url)

    @app.get("/cashier")
    @login_required("student")
    def cashier():
        return cashier_page(False)

    @app.get("/admin/cashier")
    @login_required("admin")
    def admin_cashier():
        return cashier_page(True)

    @app.post("/admin/cashier/<order_id>/confirm")
    @login_required("admin")
    def cashier_confirm(order_id):
        order = confirm_payment(order_id, g.user, "in-person")
        if order is None:
            abort(404)
        if not order["paid_at"]:
            return cashier_page(True, value=order_id), 409
        flash("Payment recorded." if order["payment_method"] == "in-person" else "This order was already paid online.")
        return redirect(url_for("admin_cashier", order_id=order_id), 303)

    @app.route("/pay/<order_id>", methods=["GET", "POST"])
    @login_required("student")
    def checkout(order_id):
        if request.method == "POST":
            order = confirm_payment(order_id, g.user, "online")
            if order is None:
                abort(404)
            if not order["paid_at"]:
                return render_template("checkout.html", order=order), 409
            return redirect(url_for("checkout", order_id=order_id), 303)
        return render_template("checkout.html", order=owns_order(order_id, detail=True))

    def qr_response(url):
        return send_file(BytesIO(qr_png(app.config["APP_BASE_URL"] + url)), mimetype="image/png")

    @app.get("/requests/<order_id>/qr")
    @login_required("student")
    def order_qr(order_id):
        owns_order(order_id)
        return qr_response(url_for("cashier", order_id=order_id))

    @app.get("/pay/<order_id>/qr")
    @login_required("student")
    def payment_qr(order_id):
        order = owns_order(order_id, detail=True)
        if not order["paid_at"] and order["academic_issues"]:
            abort(409)
        return qr_response(url_for("guest_checkout", token=payment_token(order_id)))

    @app.route("/checkout/<token>", methods=["GET", "POST"])
    def guest_checkout(token):
        if not PAYMENT_TOKEN.fullmatch(token):
            abort(404)
        if request.method == "POST":
            order = confirm_payment(None, None, "online", token=token)
            if order is None:
                abort(404)
            if request.accept_mimetypes.best == "application/json":
                return {"paid": bool(order["paid_at"])}, 200 if order["paid_at"] else 409
            if order["paid_at"]:
                return redirect(url_for("guest_checkout", token=token), 303)
        else:
            order = get_guest_order(token, detail=True)
            if order is None:
                abort(404)
        return render_template("guest_checkout.html", order=guest_payment_view(order), token=token), (
            409 if request.method == "POST" else 200
        )

    @app.get("/verify")
    @login_required("admin")
    def verification():
        query = request.args.get("document_id", "").strip().upper()[:40]
        if DOCUMENT_ID.fullmatch(query):
            return redirect(url_for("verify_document", document_id=query))
        return render_template("verify.html", query=query, document=None, searched=bool(query))

    @app.get("/verify/<document_id>")
    @login_required("admin")
    def verify_document(document_id):
        query = document_id.strip().upper()[:40]
        document = find_document(query) if DOCUMENT_ID.fullmatch(query) else None
        return render_template("verify.html", query=query, document=document, searched=True)

    @app.get("/download/<file_id>")
    @login_required()
    def download(file_id):
        record = db().execute(
            "SELECT content, order_id FROM issued_files WHERE id = ?", (file_id,),
        ).fetchone()
        if not record:
            abort(404)
        order = owns_order(record["order_id"])
        if not order["paid_at"]:
            abort(404)
        return send_file(BytesIO(record["content"]), mimetype="application/pdf",
                         as_attachment=True, download_name=f"{file_id}.pdf")

    @app.get("/requests/<order_id>/clearance")
    @login_required()
    def clearance_download(order_id):
        owns_order(order_id)
        record = db().execute("SELECT mimetype, content FROM attachments WHERE order_id = ?", (order_id,)).fetchone()
        if not record:
            abort(404)
        suffix = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}[record["mimetype"]]
        return send_file(BytesIO(record["content"]), mimetype=record["mimetype"], as_attachment=True,
                         download_name=f"clearance-{order_id}.{suffix}")

    @app.context_processor
    def common():
        return {"today": datetime.now(MANILA).date().isoformat()}

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def http_error(error):
        messages = {
            400: "Reopen the page and try again.",
            403: "This page requires a different account role.",
            404: "The page or record could not be found.",
            413: "The file is too large. Choose a clearance file of 5 MB or less.",
        }
        return render_template("error.html", code=error.code, message=messages[error.code]), error.code
