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
