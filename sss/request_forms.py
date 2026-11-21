"""Fill the supplied one-page university forms with a PDF overlay."""

from datetime import datetime
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
import reportlab

from .catalog import DENTAL_SERVICES, ID_REASONS, ID_SERVICE, LANYARD_SERVICE, MEDICAL_SERVICES, REGISTRAR


TEMPLATES = Path(__file__).with_name("form_templates")
FONT = "FormVera"
pdfmetrics.registerFont(TTFont(FONT, str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf")))
INK = HexColor("#17264c")
PAGE_WIDTH, PAGE_HEIGHT = 612, 936


def make_request_form(order):
    service = order["items"][0]["service"]
    kind = "registrar" if order["office"] == "Registrar" else service
    answers = order["answers"]
    profile = order["profile"]
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    canvas.setFillColor(INK)
    overflow = []
    used = set()

    def write(label, value, x, top, width):
        if value is None or value == "":
            return
        original = str(value).strip()
        value = original.replace("\n", " ")
        if pdfmetrics.stringWidth(value, FONT, 7) > width:
            overflow.append((label, original))
            return
        canvas.setFont(FONT, 7)
        canvas.drawString(x, PAGE_HEIGHT - top - 6, value)

    def field(key, x, top, width, label=None):
        value = answers.get(key)
        if value is not None and value != "":
            used.add(key)
            write(label or key.replace("_", " ").capitalize(), value, x, top, width)

    def mark(x, top):
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawString(x + 3, PAGE_HEIGHT - top - 6, "x")

    def select(key, choices, coordinates):
        values = answers.get(key) or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            if value in choices:
                mark(*coordinates[choices.index(value)])
            else:
                overflow.append((key.replace("_", " ").capitalize(), value))
        if values:
            used.add(key)

    def footer():
        canvas.setFont(FONT, 8)
        canvas.setFillColor(INK)
        canvas.drawString(50, 26, f"Order ID: {order['id']}")

    filed = datetime.fromisoformat(order["created_at"]).strftime("%Y-%m-%d")
    middle = answers.get("middle_name") or answers.get("middle_initial") or ""
    name = ", ".join(filter(None, (profile["last_name"], profile["first_name"], middle)))
    if middle:
        used.add("middle_name" if answers.get("middle_name") else "middle_initial")
    if kind == "registrar":
        write("Student name", name, 92, 205, 210)
        write("Student number", profile["id"], 116, 231, 180)
        write("Course", profile["course"], 88, 268, 56)
        write("College", profile["college"], 174, 268, 125)
        for key, x, top, width in [
            ("maiden_name", 135, 246, 164), ("entry_from", 122, 283, 53),
            ("entry_to", 196, 283, 103), ("graduation_date", 146, 297, 153),
            ("further_studies", 80, 389, 212), ("purpose", 105, 404, 194),
            ("address", 133, 437, 166), ("fax", 92, 465, 28),
            ("direct_line", 165, 465, 134), ("phone", 116, 482, 182),
            ("email", 106, 493, 192), ("others", 333, 493, 134),
        ]:
            field(key, x, top, width)
        select("tor_purpose", ("Evaluation", "Employment / Promotion", "For further studies"),
               [(81, 352), (81, 364), (81, 377)])
        for item in order["items"]:
            index = list(REGISTRAR).index(item["service"])
            top = [227, 256, 285, 314, 343, 372, 401, 430, 465][index]
            mark(329, top)
            write("Copies", item["quantity"], 480, top, 28)
        write("Date filed", filed, 365, 619, 194)
        appendix_top = 660
    else:
        write("Student name", name, 100, 208, 446)
        write("Student number", profile["id"], 108, 235, 24)
        write("Course", profile["course"], 222, 235, 321)
        if kind == "id-lanyard":
            write("College", profile["college"], 95, 250, 108)
            field("phone", 270, 250, 270)
            field("email", 122, 265, 420)
            select("id_service", ID_SERVICE, [(77, 322), (77, 336), (77, 349), (77, 363)])
            select("lanyard_service", LANYARD_SERVICE, [(77, 391), (77, 404)])
            select("replacement_reason", ID_REASONS,
                   [(335, 322), (335, 336), (335, 349), (335, 363), (335, 376)])
            field("replacement_other", 337, 390, 208)
            from .catalog import ID_FIELDS
            options = ID_FIELDS[2][1][0].options
            select("requirements", options, [(77, y) for y in (444, 457, 470, 483, 496, 509)])
            write("Date filed", filed, 305, 619, 148)
            appendix_top = 746
        else:
            for key, x, top, width in [
                ("age", 78, 250, 36), ("sex", 143, 250, 29),
                ("birth_date", 240, 250, 300), ("phone", 114, 265, 100),
                ("email", 273, 265, 270), ("emergency_name", 190, 280, 48),
                ("emergency_phone", 293, 280, 250), ("preferred_date", 126, 324, 52),
                ("preferred_time", 231, 324, 260),
            ]:
                field(key, x, top, width)
            if answers.get("preferred_time"):
                try:
                    mark(134 if int(answers["preferred_time"].split(":")[0]) < 12 else 195, 340)
                except ValueError:
                    pass
            if kind == "medical":
                select("clinic_service", MEDICAL_SERVICES,
                       [(77, 371), (77, 385), (77, 398), (77, 412), (335, 371), (335, 385), (335, 398)])
                for key, x, top, width in [
                    ("clinic_other", 337, 412, 205), ("complaint", 210, 457, 330),
                    ("duration", 150, 487, 390), ("allergies", 230, 502, 310),
                    ("medications", 154, 517, 385), ("condition_other", 56, 545, 480),
                ]:
                    field(key, x, top, width)
                select("conditions", ("Asthma", "Hypertension", "Diabetes", "Heart disease", "Other"),
                       [(160, 532), (208, 532), (276, 532), (329, 532), (400, 532)])
                write("Date filed", filed, 305, 608, 150)
                appendix_top = 735
            else:
                select("clinic_service", DENTAL_SERVICES,
                       [(77, 381), (77, 394), (77, 408), (77, 421), (335, 381), (335, 394), (335, 408)])
                for key, x, top, width in [
                    ("clinic_other", 337, 421, 205), ("complaint", 209, 466, 330),
                    ("last_visit", 160, 496, 54), ("pain", 286, 496, 254),
                    ("allergies", 260, 525, 280), ("medications", 154, 540, 385),
                    ("condition_other", 56, 569, 480),
                ]:
                    field(key, x, top, width)
                select("symptoms", ("Toothache", "Swelling", "Bleeding gums", "Sensitivity", "None"),
                       [(138, 511), (197, 511), (248, 511), (323, 511), (380, 511)])
                select("conditions", ("Hypertension", "Diabetes", "Heart disease", "Bleeding disorder", "Asthma", "Other"),
                       [(129, 556), (197, 556), (250, 556), (321, 556), (405, 556), (454, 556)])
                write("Date filed", filed, 305, 632, 150)
                appendix_top = 758

    for key, value in answers.items():
        if key not in used and value and key not in {"schedule"}:
            label = key.replace("_", " ").capitalize()
            if isinstance(value, list):
                value = ", ".join(value)
            overflow.append((label, str(value)))

    if overflow:
        y = PAGE_HEIGHT - appendix_top
        canvas.setFont(FONT, 8)
        canvas.drawString(50, y, "Additional request details")
        y -= 14
        for label, value in overflow:
            lines = []
            for paragraph in f"{label}: {value}".splitlines():
                # Split very long unbroken input before wrapping it to the page.
                words = []
                for word in paragraph.split():
                    while pdfmetrics.stringWidth(word, FONT, 8) > 500:
                        cut = len(word)
                        while pdfmetrics.stringWidth(word[:cut], FONT, 8) > 500:
                            cut -= 1
                        words.append(word[:cut])
                        word = word[cut:]
                    words.append(word)
                lines.extend(simpleSplit(" ".join(words), FONT, 8, 510) or [""])
            for line in lines:
                if y < 48:
                    footer()
                    canvas.showPage()
                    canvas.setFillColor(INK)
                    canvas.setFont(FONT, 8)
                    y = PAGE_HEIGHT - 48
                canvas.drawString(50, y, line)
                y -= 11
            y -= 4
    footer()
    canvas.save()

    template = PdfReader(TEMPLATES / f"{kind}.pdf")
    overlays = PdfReader(BytesIO(buffer.getvalue()))
    result = PdfWriter()
    result.add_page(template.pages[0])
    result.pages[0].merge_page(overlays.pages[0])
    for page in overlays.pages[1:]:
        result.add_page(page)
    output = BytesIO()
    result.write(output)
    return output.getvalue()
