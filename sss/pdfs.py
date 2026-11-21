from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from .catalog import (
    CLINIC_GUIDANCE, DECLARATIONS, GRADE_FIELDS, OSAS, REGISTRAR_DETAILS, UNIT_PRICE, response_groups,
)


NAVY = colors.HexColor("#17264C")
BLUE = colors.HexColor("#2452A5")
MUTED = colors.HexColor("#53647F")
LINE = colors.HexColor("#DBE3EF")
PALE = colors.HexColor("#F3F6FB")
LOGO = Path(__file__).with_name("static") / "isatu.png"
WIDTH, HEIGHT = letter
MARGIN = 42
CONTENT_WIDTH = WIDTH - 2 * MARGIN

TITLE = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=25, leading=29, textColor=NAVY)
SUBTITLE = ParagraphStyle("Subtitle", fontSize=10, leading=15, textColor=MUTED, spaceAfter=12)
SECTION = ParagraphStyle("Section", fontName="Helvetica-Bold", fontSize=12, leading=16,
                         textColor=NAVY, spaceBefore=14, spaceAfter=6, keepWithNext=True)
BODY = ParagraphStyle("Body", fontSize=9, leading=14, textColor=NAVY, spaceAfter=5, splitLongWords=True)
DIPLOMA_NAME = ParagraphStyle("DiplomaName", parent=TITLE, fontSize=32, leading=38, alignment=TA_CENTER)
DIPLOMA_LABEL = ParagraphStyle("DiplomaLabel", parent=SECTION, alignment=TA_CENTER, keepWithNext=False)
DIPLOMA_NOTE = ParagraphStyle("DiplomaNote", parent=BODY, alignment=TA_CENTER)


def qr_png(value):
    qr = qrcode.QRCode(box_size=7, border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(value)
    qr.make(fit=True)
    buffer = BytesIO()
    qr.make_image(fill_color="#111e36", back_color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def paragraph(value, style=BODY):
    return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)


def panel(rows, widths=None):
    table = Table(
        [[paragraph(value) for value in row] for row in rows],
        colWidths=widths or [CONTENT_WIDTH * .34, CONTENT_WIDTH * .66],
        hAlign="LEFT",
        splitInRow=1,
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), (colors.white, PALE)),
        ("LINEBELOW", (0, 0), (-1, -1), .4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def date_label(iso):
    return datetime.fromisoformat(iso).strftime("%d %B %Y")


def price(amount):
    return f"PHP {amount / 100:,.2f}"


def add_answers(story, groups, answers):
    for title, fields in groups:
        rows = []
        for field in fields:
            value = answers.get(field.name)
            if isinstance(value, list):
                value = "\n".join(value)
            if value:
                rows.append((field.label, value))
        if rows:
            story.extend((paragraph(title, SECTION), panel(rows)))


def student_rows(profile, answers):
    return [
        ("Name", profile["name"]),
        ("Last name", profile["last_name"]),
        ("First name", profile["first_name"]),
        ("Middle name / initial", answers.get("middle_name") or answers.get("middle_initial") or "—"),
        ("Student number", profile["id"]),
        ("Course / year / section", profile["course"]),
        ("College", profile["college"]),
    ]


def payment_rows(order, item, copy):
    return [
        ("Order ID", order["id"]),
        ("Payment reference", order["receipt"]),
        ("Payment date", date_label(order["paid_at"])),
        ("Payment method", "Simulated online" if order["payment_method"] == "online" else "In person"),
        ("Copy", f"{copy} of {item['quantity']}"),
        ("Amount for this copy", price(UNIT_PRICE)),
        ("Total paid for order", price(order["total"])),
    ]


def request_story(order, item, copy):
    profile = order["profile"]
    answers = order["answers"]
    service = item["service"]
    registrar = order["office"] == "Registrar"
    code = "OUR-QF-01" if registrar else OSAS[service][3]
    title = "Registrar Request Form" if registrar else f"{item['title']} Request Form"
    story = [
        paragraph(title, TITLE),
        paragraph(f"{code}  |  {item['title']}" if registrar else code, SUBTITLE),
    ]
    if service in CLINIC_GUIDANCE and not registrar:
        story.append(paragraph(CLINIC_GUIDANCE[service]))
    story.extend((paragraph("Student information", SECTION), panel(student_rows(profile, answers))))
    if registrar:
        groups = REGISTRAR_DETAILS
        if service == "grades":
            groups = (("Certification of Grades coverage", GRADE_FIELDS),) + groups
        if service == "good-moral":
            story.append(paragraph("Supporting document received: clearance copy."))
    else:
        groups = response_groups(order["office"], order["items"], answers)
    add_answers(story, groups, answers)
    story.extend((
        paragraph("Payment details", SECTION),
        panel(payment_rows(order, item, copy)),
        paragraph("Declaration", SECTION),
        paragraph(DECLARATIONS["registrar" if registrar else service]),
        paragraph(f"Attested by {profile['name']}  |  Filed {date_label(order['created_at'])}"),
    ))
    if registrar:
        staff = ("Receiving staff", "Date received", "Date of release")
    elif service == "id-lanyard":
        staff = ("Received by", "Date received", "Verified by", "Released on", "Claimed by", "Remarks")
    else:
        attendant = "Attending dentist" if service == "dental" else "Attending physician / nurse"
        staff = ("Appointment date", "Time", attendant, "Status", "Received by", "Remarks")
    story.extend((paragraph("For office use", SECTION), panel([(field, "______________________") for field in staff])))
    return story


def sample_story(order, item, copy):
    student = order["profile"]
    if item["service"] == "diploma":
        return [
            Spacer(1, 39),
            paragraph("SAMPLE DIPLOMA", DIPLOMA_LABEL),
            Spacer(1, 20),
            paragraph("Iloilo Science and Technology University", DIPLOMA_LABEL),
            paragraph("This sample diploma is presented to", DIPLOMA_NOTE),
            Spacer(1, 12),
            paragraph(student["name"], DIPLOMA_NAME),
            Spacer(1, 12),
            paragraph(order.get("sample_program") or "Bachelor of Science in Information Technology", DIPLOMA_LABEL),
            paragraph(student["college"], DIPLOMA_NOTE),
            Spacer(1, 26),
            paragraph("Illustrative degree document for the ISATU - SSS demonstration.", DIPLOMA_NOTE),
            paragraph(f"Request {order['id']}  |  Copy {copy} of {item['quantity']}", DIPLOMA_NOTE),
        ]
    entry_year = int(order["answers"]["entry_from"])
    purpose = order["answers"]["tor_purpose"]
    if order["answers"].get("further_studies"):
        purpose += f" · {order['answers']['further_studies']}"
    return [
        paragraph("Sample Transcript of Records", TITLE),
        paragraph("Illustrative courses and grades for the ISATU - SSS demonstration.", SUBTITLE),
        paragraph("Student information", SECTION),
        panel([
            ("Name", student["name"]), ("Student number", student["id"]),
            ("Course / year / section", student["course"]), ("College", student["college"]),
        ]),
        paragraph(f"Illustrative grades  |  First semester, {entry_year}-{entry_year + 1}", SECTION),
        panel([
            ("Course", "Descriptive title", "Units", "Sample grade"),
            *order.get("sample_transcript", [
            ("IT 101", "Introduction to Computing", 3, "1.75"),
            ("IT 102", "Computer Programming 1", 3, "1.50"),
            ("GE 101", "Understanding the Self", 3, "1.75"),
            ("GE 102", "Mathematics in the Modern World", 3, "2.00"),
            ]),
        ], (74, 258, 62, 134)),
        paragraph("Request details", SECTION),
        panel([
            ("Purpose", purpose), ("Order ID", order["id"]),
            ("Copy", f"{copy} of {item['quantity']}"), ("Issued", date_label(order["paid_at"])),
        ]),
    ]


def make_pdf(order, item, copy, file_id, verify_url):
    output = BytesIO()
    document = BaseDocTemplate(output, pagesize=letter, title=item["title"], author="ISATU - SSS")
    qr = ImageReader(BytesIO(qr_png(verify_url))) if verify_url else None

    def decorate(canvas, page):
        canvas.setFillColor(NAVY)
        canvas.drawImage(str(LOGO), MARGIN, HEIGHT - 61, 34, 34, mask="auto")
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(MARGIN + 43, HEIGHT - 42, "ILOILO SCIENCE AND TECHNOLOGY UNIVERSITY")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 9)
        office = "Office of the University Registrar" if order["office"] == "Registrar" else (
            "Office of Student Affairs and Services"
        )
        canvas.drawString(MARGIN + 43, HEIGHT - 55, office)
        canvas.setStrokeColor(LINE)
        canvas.line(MARGIN, HEIGHT - 71, WIDTH - MARGIN, HEIGHT - 71)
        canvas.setFillColor(BLUE)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(MARGIN, 26, "PROTOTYPE  |  FOR DEMONSTRATION")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 8)
        if page.page == 1 and qr:
            canvas.setStrokeColor(LINE)
            canvas.line(MARGIN, 114, WIDTH - MARGIN, 114)
            canvas.setFillColor(NAVY)
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawString(MARGIN, 84, file_id)
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica", 8)
            canvas.drawString(MARGIN, 68, "Scan to open the ISATU - SSS verification record.")
            canvas.drawImage(qr, WIDTH - MARGIN - 76, 32, 76, 76)
        canvas.drawRightString(WIDTH - MARGIN, 26, f"Page {page.page}")

    def frame(bottom):
        return Frame(MARGIN, bottom, CONTENT_WIDTH, HEIGHT - 92 - bottom,
                     leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    document.addPageTemplates((
        PageTemplate("first", frames=[frame(128 if qr else 47)], onPage=decorate,
                     autoNextPageTemplate="continuation"),
        PageTemplate("continuation", frames=[frame(47)], onPage=decorate),
    ))
    sample = order["office"] == "Registrar" and item["service"] in {"tor", "diploma"}
    document.build(sample_story(order, item, copy) if sample else request_story(order, item, copy))
    return output.getvalue()
