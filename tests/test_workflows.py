from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from hashlib import scrypt
from importlib import import_module
from io import BytesIO
from threading import Barrier
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from PIL import Image
from pypdf import PdfReader

from sss import create_app
from sss.accounts import DEMO_ACCOUNTS
from sss.catalog import DENTAL_SERVICES, MANILA, MEDICAL_SERVICES, REGISTRAR

database = import_module("sss.db")
STUDENT = "2025-4611-U"
OTHER_STUDENT = "2024-5587-I"
ADMIN = "admin_ako"
TEST_ADMIN_PASSWORD = "test-admin-only"


@pytest.fixture
def app(tmp_path):
    accounts = {key: dict(value) for key, value in DEMO_ACCOUNTS.items()}
    admin = accounts[ADMIN]
    admin["digest"] = scrypt(TEST_ADMIN_PASSWORD.encode(), salt=bytes.fromhex(admin["salt"]),
                             n=2**14, r=8, p=1, dklen=32).hex()
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-session-key",
        "WTF_CSRF_ENABLED": False,
        "DATABASE": str(tmp_path / "test.sqlite3"),
        "ACCOUNTS": accounts,
    })


def login(client, identity):
    password = TEST_ADMIN_PASSWORD if identity == ADMIN else DEMO_ACCOUNTS[identity.casefold()]["last_name"]
    response = client.post("/login", data={"identity": identity, "password": password})
    assert response.status_code == 303
    return client


def registrar_form(*services, **fields):
    return {
        "services": list(services), "request_key": uuid4().hex,
        "entry_from": "2024", "entry_to": "2026", "address": "La Paz, Iloilo City",
        "phone": "09123456789", "email": "student@example.test", "purpose": "School requirement",
        "tor_purpose": "Evaluation", "consent": "yes",
        **fields,
    }


def submit(client, data, path="/registrar"):
    response = client.post(path, data=data)
    assert response.status_code == 303, response.get_data(as_text=True)
    assert "Request received" in client.get(response.location).get_data(as_text=True)
    return urlsplit(response.location).path.split("/")[-1]


def files_for(app, order_id):
    with app.app_context():
        return database.get_order(order_id, detail=True)["files"]


def pdf_from(client, file_id):
    response = client.get(f"/download/{file_id}")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "attachment" in response.headers["Content-Disposition"]
    return PdfReader(BytesIO(response.data))


def test_login_and_role_guards(app):
    anonymous = app.test_client()
    assert anonymous.get("/cashier").status_code == 302
    assert anonymous.get("/verify/DOC-0123456789ABCDEF").location.startswith("/login?next=")
    assert anonymous.post("/login", data={"identity": STUDENT, "password": "invalid"}).status_code == 401
    for identity in (STUDENT, OTHER_STUDENT, "2024-1263-A"):
        student = login(app.test_client(), identity)
        assert student.get("/").status_code == 200
        assert student.get("/admin/requests").status_code == 403
    admin = login(app.test_client(), ADMIN)
    assert admin.get("/").status_code == 200
    assert admin.get("/registrar").status_code == 403


def test_online_payment_documents_and_ownership(app):
    student = login(app.test_client(), STUDENT)
    other = login(app.test_client(), OTHER_STUDENT)
    admin = login(app.test_client(), ADMIN)
    data = registrar_form("diploma", "tor", copies_diploma="2")
    order_id = submit(student, data)
    assert student.post("/registrar", data=data).location.endswith(f"{order_id}?received=1")
    assert not files_for(app, order_id)
    assert other.get(f"/requests/{order_id}").status_code == 404
    assert other.post(f"/pay/{order_id}").status_code == 404
    assert student.get(f"/requests/{order_id}/qr").mimetype == "image/png"
    assert student.get(f"/pay/{order_id}/qr").mimetype == "image/png"
    cashier = student.get(f"/cashier?order_id={order_id}").get_data(as_text=True)
    assert "₱150.00" in cashier
    assert 'target="_blank"' in cashier
    assert student.post(f"/pay/{order_id}").status_code == 303
    assert "Payment complete" in student.get(f"/pay/{order_id}").get_data(as_text=True)
    files = files_for(app, order_id)
    assert len({file["id"] for file in files}) == 3
    assert {file["title"] for file in files} == {"Diploma", "Transcript of Records"}
    for file in files:
        assert file["verifiable"]
        pdf = pdf_from(student, file["id"])
        assert file["id"] in pdf.pages[0].extract_text()
        assert "DEMONSTRATION" in pdf.pages[0].extract_text()
        assert len(pdf.pages[0].images) == 2
        assert other.get(f"/download/{file['id']}").status_code == 404
        assert f"/verify/{file['id']}" in admin.get(f"/verify?document_id={file['id']}").location
        verification = admin.get(f"/verify/{file['id']}").get_data(as_text=True)
        assert file["id"] in verification
        assert f"<dt>Copy</dt><dd>{file['copy']}</dd>" in verification
        assert admin.get(f"/download/{file['id']}").data == student.get(f"/download/{file['id']}").data
    assert student.post(f"/pay/{order_id}").status_code == 303
    assert files_for(app, order_id) == files


def test_registrar_validation_clearance_and_multipage_pdf(app):
    student = login(app.test_client(), STUDENT)
    admin = login(app.test_client(), ADMIN)
    assert b"Attach a clearance" in student.post("/registrar", data=registrar_form("good-moral")).data
    assert b"Specify the document" in student.post("/registrar", data=registrar_form("others")).data
    reversed_years = registrar_form("grades", grade_from_year="2025–2026", grade_to_year="2024–2025",
                                   grade_from_sem="First semester", grade_to_sem="First semester")
    assert b"End year and semester" in student.post("/registrar", data=reversed_years).data
    payload = BytesIO()
    Image.new("RGB", (20, 20), "white").save(payload, format="PNG")
    clearance = payload.getvalue()
    selected = [code for code in REGISTRAR if code not in {"diploma", "tor"}]
    data = registrar_form(
        *selected,
        clearance=(BytesIO(clearance), "clearance.png"),
        grade_from_year="2024–2025", grade_to_year="2025–2026",
        grade_from_sem="First semester", grade_to_sem="Second semester",
        purpose="Academic requirement with detailed context.\n" * 35,
        address="Iloilo City address information.\n" * 35,
        others="Sample eligibility record",
    )
    order_id = submit(student, data)
    assert admin.get(f"/requests/{order_id}/clearance").data == clearance
    assert login(app.test_client(), OTHER_STUDENT).get(f"/requests/{order_id}/clearance").status_code == 404
    assert admin.post(f"/admin/cashier/{order_id}/confirm").status_code == 303
    assert "₱350.00" in student.get(f"/requests/{order_id}").get_data(as_text=True)
    files = files_for(app, order_id)
    assert len(files) == 7
    assert any(file["title"] == "Sample eligibility record" for file in files)
    grade = next(file for file in files if file["title"] == "Certification of Grades")
    pdf = pdf_from(student, grade["id"])
    assert len(pdf.pages) >= 2
    assert len(pdf.pages[0].images) == 2
    for page in pdf.pages[1:]:
        assert len(page.images) == 1
        assert grade["id"] not in page.extract_text()
    complete_text = "\n".join(page.extract_text() for page in pdf.pages)
    assert "Second semester" in complete_text
    assert "2025–2026" in complete_text


@pytest.mark.parametrize("service,service_fields,expected", [
    ("id-lanyard", {"id_service": "Replacement of ID", "replacement_reason": "Lost"}, "Replacement of ID"),
    ("medical", {"clinic_service": MEDICAL_SERVICES[0]}, "General medical consultation"),
    ("dental", {"clinic_service": DENTAL_SERVICES[0], "pain": "4"}, "Oral examination"),
])
def test_osas_forms_and_admin_details(app, service, service_fields, expected):
    student = login(app.test_client(), STUDENT)
    admin = login(app.test_client(), ADMIN)
    today = datetime.now(MANILA).date()
    details = {
        "request_key": uuid4().hex, "consent": "yes",
        "phone": "09123456789", "email": "student@example.test",
        "age": "20", "sex": "Male", "birth_date": "2006-08-14",
        "emergency_name": "Demo contact", "emergency_phone": "09120000000",
        "preferred_date": (today + timedelta(days=2)).isoformat(), "preferred_time": "10:30",
        "schedule": "Morning", "complaint": "Demo appointment reason",
        **service_fields,
    }
    order_id = submit(student, details, f"/osas/{service}")
    assert expected in admin.get(f"/admin/requests/{order_id}").get_data(as_text=True)
    assert admin.post(f"/admin/cashier/{order_id}/confirm").status_code == 303
    [file] = files_for(app, order_id)
    assert not file["verifiable"]
    assert "₱50.00" in student.get(f"/requests/{order_id}").get_data(as_text=True)
    pdf = pdf_from(student, file["id"])
    assert expected in " ".join(page.extract_text() for page in pdf.pages)
    assert all(len(page.images) == 1 for page in pdf.pages)


def test_concurrent_payment_and_persistence(app):
    order_id = submit(login(app.test_client(), STUDENT), registrar_form("diploma", copies_diploma="2"))
    ready = Barrier(2)

    def confirm(identity, path):
        client = login(app.test_client(), identity)
        ready.wait(timeout=5)
        return client.post(path).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        online = executor.submit(confirm, STUDENT, f"/pay/{order_id}")
        in_person = executor.submit(confirm, ADMIN, f"/admin/cashier/{order_id}/confirm")
        assert online.result(timeout=10) == in_person.result(timeout=10) == 303

    with app.app_context():
        order = database.get_order(order_id, detail=True)
    assert len(order["files"]) == 2
    assert order["payment_method"] in {"online", "in-person"}
    restarted = create_app({
        "TESTING": True, "SECRET_KEY": "test-session-key",
        "WTF_CSRF_ENABLED": False, "DATABASE": app.config["DATABASE"],
        "ACCOUNTS": app.config["ACCOUNTS"],
    })
    assert files_for(restarted, order_id) == order["files"]


def test_generation_rolls_back_partial_payment(app, monkeypatch):
    student = login(app.test_client(), STUDENT)
    order_id = submit(student, registrar_form("diploma", copies_diploma="2"))
    original = database.make_pdf

    def fail_second(order, item, copy, file_id, url):
        if copy == 2:
            raise RuntimeError("demonstration of a PDF generation failure")
        return original(order, item, copy, file_id, url)

    with monkeypatch.context() as isolated:
        isolated.setattr(database, "make_pdf", fail_second)
        with pytest.raises(RuntimeError):
            student.post(f"/pay/{order_id}")
    with app.app_context():
        order = database.get_order(order_id, detail=True)
        assert not order["paid_at"]
        assert not order["files"]
    assert student.post(f"/pay/{order_id}").status_code == 303
    assert len(files_for(app, order_id)) == 2


def test_state_changes_require_csrf(app):
    app.config["WTF_CSRF_ENABLED"] = True
    assert app.test_client().post("/login", data={"identity": STUDENT, "password": "invalid"}).status_code == 400


def test_guest_payment_is_scoped_and_updates_owner_status(app):
    student = login(app.test_client(), STUDENT)
    order_id = submit(student, registrar_form("others", others="Private special instruction"))
    details = student.get(f"/requests/{order_id}").get_data(as_text=True)
    assert 'href="/checkout/' in details
    token = details.split('href="/checkout/', 1)[1].split('"', 1)[0]
    assert len(token) == 43
    guest = app.test_client()
    page = guest.get(f"/checkout/{token}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Pay ₱50.00" in html and "Others (Specify)" in html
    assert "Private special instruction" not in html and "Keane Prudente" not in html
    assert guest.get(f"/checkout/{order_id}").status_code == 404
    assert guest.get(f"/checkout/{token}/status").json == {"paid": False}
    assert student.get("/payments/status").json == {"paid_orders": []}
    assert guest.get("/payments/status").status_code == 401

    for _ in range(2):
        result = guest.post(f"/checkout/{token}", data={"total": "0"}, headers={"Accept": "application/json"})
        assert result.status_code == 200 and result.json == {"paid": True}
    assert guest.get(f"/checkout/{token}/status").json == {"paid": True}
    assert student.get("/payments/status").json == {"paid_orders": [order_id]}
    assert login(app.test_client(), OTHER_STUDENT).get("/payments/status").json == {"paid_orders": []}
    [document] = files_for(app, order_id)
    assert guest.get(f"/download/{document['id']}").status_code == 302
    assert student.get(f"/download/{document['id']}").status_code == 200
    with app.app_context():
        order = database.get_order(order_id, detail=True)
        assert order["total"] == 5000
        assert order["paid_by"] == "guest-checkout"


def test_guest_checkout_requires_csrf_but_not_sign_in(app):
    student = login(app.test_client(), STUDENT)
    order_id = submit(student, registrar_form("diploma"))
    with app.app_context():
        token = database.payment_token(order_id)
    app.config["WTF_CSRF_ENABLED"] = True
    guest = app.test_client()
    path = f"/checkout/{token}"
    assert guest.post(path).status_code == 400
    html = guest.get(path).get_data(as_text=True)
    csrf = html.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    assert guest.post(path, data={"csrf_token": csrf}).status_code == 303


def test_registrar_attendance_and_grade_guardrails(app):
    student = login(app.test_client(), STUDENT)
    filed = datetime.now(MANILA).year
    bad_attendance = registrar_form("tor", entry_from="2025", entry_to=str(filed + 2), graduation_date="2007-08-09")
    response = student.post("/registrar", data=bad_attendance)
    assert response.status_code == 422
    assert b"Graduation cannot precede the first year of attendance" in response.data

    grade_request = registrar_form("grades", grade_from_year="2024-2025", grade_from_sem="First semester",
                                   grade_to_year="2025-2026", grade_to_sem="Second semester")
    outside_attendance = {**grade_request, "entry_from": "2025"}
    assert b"within the years you attended" in student.post("/registrar", data=outside_attendance).data
    after_graduation = {**grade_request, "graduation_date": "2026-01-01",
                        "grade_to_sem": "Summer term"}
    assert b"cannot extend past graduation" in student.post("/registrar", data=after_graduation).data
    future = {**grade_request, "grade_to_year": f"{filed}-{filed + 1}", "grade_to_sem": "Second semester"}
    assert b"period that has already started" in student.post("/registrar", data=future).data


def test_legacy_invalid_academic_dates_block_new_payments(app):
    student = login(app.test_client(), STUDENT)
    admin = login(app.test_client(), ADMIN)
    with app.app_context():
        account = DEMO_ACCOUNTS[STUDENT.casefold()]
        order_id = database.create_order(
            account, "Registrar", [("tor", REGISTRAR["tor"], 1)],
            {"entry_from": "2025", "entry_to": "2028", "graduation_date": "2007-08-09"}, None, uuid4().hex,
        )
        token = database.payment_token(order_id)
    assert b"Academic dates need review" in student.get(f"/requests/{order_id}").data
    assert admin.post(f"/admin/cashier/{order_id}/confirm").status_code == 409
    assert student.post(f"/pay/{order_id}").status_code == 409
    assert app.test_client().post(f"/checkout/{token}").status_code == 409
    assert not files_for(app, order_id)


def test_clinic_derives_age_with_single_preferred_time(app):
    student = login(app.test_client(), STUDENT)
    html = student.get("/osas/medical").get_data(as_text=True)
    assert 'name="schedule"' not in html and 'name="age"' not in html
    date = (datetime.now(MANILA).date() + timedelta(days=1)).isoformat()
    order_id = submit(student, {
        "request_key": uuid4().hex, "consent": "yes",
        "phone": "09123456789", "email": "student@example.test",
        "sex": "Male", "birth_date": "2006-05-01",
        "emergency_name": "Demo contact", "emergency_phone": "09120000000",
        "preferred_date": date, "preferred_time": "15:00",
        "clinic_service": MEDICAL_SERVICES[0], "complaint": "Demo appointment reason",
    }, "/osas/medical")
    with app.app_context():
        answers = database.get_order(order_id, detail=True)["answers"]
        assert int(answers["age"]) >= 18 and "schedule" not in answers
        assert answers["preferred_time"] == "15:00"


def test_student_account_lifecycle(app):
    from re import search

    visitor = app.test_client()
    form = {
        "first_name": "Demo", "middle_name": "", "last_name": "Sample",
        "program": "BSIT", "year_level": "1", "section": "A", "college": "Computing",
        "password": "demo-password", "confirm_password": "demo-password",
    }
    result = visitor.post("/signup", data=form, follow_redirects=True)
    identity = search(r"\d{4}-\d{4}-[AUI]", result.get_data(as_text=True)).group()
    assert visitor.post("/login", data={"identity": identity, "password": "demo-password"}).status_code == 303
    other_session = app.test_client()
    other_session.post("/login", data={"identity": identity, "password": "demo-password"})
    admin = login(app.test_client(), ADMIN)
    edit = {**form, "last_name": "Updated"}
    assert admin.post(f"/admin/students/{identity}/edit", data=edit).status_code == 303
    assert admin.post(f"/admin/students/{identity}/reset-password").status_code == 303
    assert other_session.get("/requests").status_code == 302
    assert visitor.post("/login", data={"identity": identity, "password": "Updated"}).status_code == 303
    assert visitor.post("/account/password", data={
        "current_password": "Updated", "password": "new-password", "confirm_password": "new-password",
    }).status_code == 303
    assert visitor.get("/requests").status_code == 200
    order_ids = []
    for _ in range(2):
        order = submit(visitor, registrar_form("tor"))
        assert visitor.post(f"/pay/{order}").status_code == 303
        order_ids.append(order)
    with app.app_context():
        transcript = database.db().execute("SELECT transcript FROM students WHERE id=?", (identity,)).fetchone()[0]
    pdf_texts = []
    for order in order_ids:
        [file] = files_for(app, order)
        pdf_texts.append(" ".join(page.extract_text() for page in pdf_from(visitor, file["id"]).pages))
    import json
    for _, title, _, _ in json.loads(transcript):
        assert all(title in text for text in pdf_texts)
    unpaid = submit(visitor, registrar_form("diploma"))
    with app.app_context():
        token = database.payment_token(unpaid)
    assert admin.post(f"/admin/students/{identity}/deactivate").status_code == 303
    assert app.test_client().post(f"/checkout/{token}").status_code == 409
    assert admin.post(f"/admin/cashier/{unpaid}/confirm").status_code == 409
    assert visitor.get("/requests").status_code == 302
    assert admin.post(f"/admin/students/{identity}/delete", data={"confirm_id": identity}).status_code == 303
    with app.app_context():
        assert database.db().execute("SELECT 1 FROM students WHERE id=?", (identity,)).fetchone() is None
        assert database.db().execute("SELECT 1 FROM orders WHERE student_id=?", (identity,)).fetchone() is None
        database.init_db()
        assert database.db().execute("SELECT 1 FROM students WHERE id=?", (identity,)).fetchone() is None
