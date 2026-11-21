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

from .catalog import DENTAL_SERVICES, ID_FIELDS, ID_REASONS, ID_SERVICE, LANYARD_SERVICE, MEDICAL_SERVICES, REGISTRAR


TEMPLATES = Path(__file__).with_name("form_templates")
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FALLBACK_FONT = "FormVera"
pdfmetrics.registerFont(TTFont(FALLBACK_FONT, str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf")))
# The supplied Word-exported templates use Arial Narrow (~82% width of Helvetica/Arial).
HORIZ_SCALE = 82
INK = HexColor("#111111")
FOOTER_INK = HexColor("#333333")
PAGE_WIDTH, PAGE_HEIGHT = 612, 936
BASE_SIZE = 9.5
MIN_SIZE = 7.0


def _pick_font(text, bold=False):
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        return FALLBACK_FONT, 100
    return (FONT_BOLD if bold else FONT), HORIZ_SCALE


def _measure(text, size, bold=False):
    font, scale = _pick_font(text, bold=bold)
    return pdfmetrics.stringWidth(text, font, size) * (scale / 100.0)


def _draw(canvas, x, y, text, size=BASE_SIZE, *, bold=False, align="left"):
    font, scale = _pick_font(text, bold=bold)
    if align == "center":
        x -= _measure(text, size, bold=bold) / 2.0
    tx = canvas.beginText()
    tx.setTextOrigin(x, y)
    tx.setFont(font, size)
    tx.setHorizScale(scale)
    tx.textOut(text)
    canvas.drawText(tx)


def _wrap_for_width(text, size, width):
    """Wrap text into lines that fit within `width` at condensed `size`."""
    font, scale = _pick_font(text)
    unscaled = width / (scale / 100.0)
    words = []
    for word in text.split():
        while pdfmetrics.stringWidth(word, font, size) > unscaled:
            cut = len(word)
            while cut > 1 and pdfmetrics.stringWidth(word[:cut], font, size) > unscaled:
                cut -= 1
            words.append(word[:cut])
            word = word[cut:]
        words.append(word)
    return simpleSplit(" ".join(words), font, size, unscaled) or [""]


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

    def write(label, value, x, y, width, *, size=BASE_SIZE, min_size=MIN_SIZE, align="left"):
        if value is None or value == "":
            return
        original = str(value).strip()
        if not original:
            return
        text = " ".join(original.split())
        chosen = size
        while chosen > min_size and _measure(text, chosen) > width:
            chosen = round(chosen - 0.5, 1)
        if _measure(text, chosen) > width:
            overflow.append((label, original))
            return
        _draw(canvas, x, y, text, chosen, align=align)

    def write_lines(label, value, slots, *, size=9.0, min_size=7.5):
        """Fill one or more (x, y, width) underline slots before overflowing."""
        if value is None or value == "":
            return
        original = str(value).strip()
        if not original:
            return
        text = " ".join(original.split())
        chosen = size
        while chosen >= min_size:
            remaining = text.split()
            placed = []
            for slot_x, slot_y, slot_w in slots:
                line = []
                while remaining:
                    candidate = " ".join(line + [remaining[0]])
                    if _measure(candidate, chosen) <= slot_w:
                        line.append(remaining.pop(0))
                    else:
                        break
                placed.append((slot_x, slot_y, " ".join(line)))
            if not remaining:
                for slot_x, slot_y, content in placed:
                    if content:
                        _draw(canvas, slot_x, slot_y, content, chosen)
                return
            chosen = round(chosen - 0.5, 1)
        overflow.append((label, original))

    def field(key, x, y, width, label=None, **kwargs):
        value = answers.get(key)
        if value is not None and value != "":
            used.add(key)
            write(label or key.replace("_", " ").capitalize(), value, x, y, width, **kwargs)

    def multi_field(key, slots, label=None):
        value = answers.get(key)
        if value is not None and value != "":
            used.add(key)
            write_lines(label or key.replace("_", " ").capitalize(), value, slots)

    def mark(x, y):
        # Draw a crisp vector checkmark centered inside '[   ]' (font-independent across all PDF viewers).
        canvas.saveState()
        canvas.setStrokeColor(INK)
        canvas.setLineWidth(1.1)
        canvas.setLineCap(1)
        canvas.setLineJoin(1)
        path = canvas.beginPath()
        path.moveTo(x + 3.2, y + 3.4)
        path.lineTo(x + 5.1, y + 1.2)
        path.lineTo(x + 8.6, y + 6.4)
        canvas.drawPath(path, stroke=1, fill=0)
        canvas.restoreState()

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
        canvas.setFillColor(FOOTER_INK)
        _draw(canvas, 50, 26, f"Order ID: {order['id']}", 8.5)
        canvas.setFillColor(INK)

    filed = datetime.fromisoformat(order["created_at"]).strftime("%Y-%m-%d")
    middle = answers.get("middle_name") or answers.get("middle_initial") or ""
    name = ", ".join(filter(None, (profile["last_name"], profile["first_name"], middle)))
    if middle:
        used.add("middle_name" if answers.get("middle_name") else "middle_initial")

    if kind == "registrar":
        # Exact baseline coordinates extracted from sss/form_templates/registrar.pdf
        write("Student name", name, 84, 724.4, 214)
        write("Student number", profile["id"], 105, 698.2, 192)
        write("Course", profile["course"], 88, 661.2, 50)
        write("College", profile["college"], 182, 661.2, 118, min_size=6.5)
        for key, x, y, width in [
            ("maiden_name", 113, 683.2, 184),
            ("entry_from", 124, 646.2, 51),
            ("entry_to", 202, 646.2, 95),
            ("graduation_date", 131, 631.2, 166),
            ("further_studies", 82, 539.9, 214),
            ("purpose", 96, 524.9, 201),
            ("fax", 89, 462.6, 29),
            ("direct_line", 172, 462.6, 125),
            ("phone", 117, 447.6, 180),
            ("email", 113, 432.6, 184),
            ("others", 331, 435.3, 138),
        ]:
            field(key, x, y, width, min_size=6.5 if key == "fax" else MIN_SIZE)
        multi_field("address", [(134, 492.6, 164), (57, 477.6, 241)], "Permanent address")
        select("tor_purpose", ("Evaluation", "Employment / Promotion", "For further studies"),
               [(80.8, 576.5), (80.8, 564.0), (80.8, 551.5)])
        row_ys = [700.9, 671.9, 642.9, 613.9, 584.9, 555.9, 526.9, 497.9, 462.9]
        total_copies = 0
        for item in order["items"]:
            index = list(REGISTRAR).index(item["service"])
            row_y = row_ys[index]
            mark(328.8, row_y)
            write("Copies", item["quantity"], 494.5, row_y + 1.4, 34, align="center")
            total_copies += item["quantity"]
        if total_copies:
            write("Total copies", total_copies, 494.5, 404.3, 34, align="center")
        write("Date filed", filed, 358, 310.0, 190)
        appendix_y = 276
    else:
        # Exact baseline coordinates extracted from sss/form_templates/{id-lanyard,medical,dental}.pdf
        write("Student name", name, 84, 721.0, 456)
        write("Student number", profile["id"], 103, 693.8, 19)
        write("Course", profile["course"], 223, 693.8, 318)
        if kind == "id-lanyard":
            write("College", profile["college"], 90, 678.8, 122, min_size=6.5)
            field("phone", 273, 678.8, 268)
            field("email", 115, 663.8, 426)
            select("id_service", ID_SERVICE,
                   [(76.8, 605.8), (76.8, 592.2), (76.8, 578.8), (76.8, 565.2)])
            select("lanyard_service", LANYARD_SERVICE,
                   [(76.8, 537.2), (76.8, 523.8)])
            select("replacement_reason", ID_REASONS,
                   [(334.6, 605.8), (334.6, 592.2), (334.6, 578.8), (334.6, 565.2), (334.6, 551.8)])
            field("replacement_other", 337, 538.6, 204)
            options = ID_FIELDS[2][1][0].options
            select("requirements", options,
                   [(76.8, y) for y in (484.1, 471.1, 458.1, 445.1, 432.1, 419.1)])
            write("Date filed", filed, 416, 310.2, 160, align="center")
            appendix_y = 192
        else:
            for key, x, y, width in [
                ("age", 76, 678.8, 40),
                ("sex", 147, 678.8, 28),
                ("birth_date", 238, 678.8, 302),
                ("phone", 105, 663.8, 96),
                ("email", 273, 663.8, 268),
                ("emergency_name", 162, 648.8, 50),
                ("emergency_phone", 273, 648.8, 268),
                ("preferred_date", 115, 604.6, 46),
                ("preferred_time", 233, 604.6, 308),
            ]:
                field(key, x, y, width)
            if answers.get("preferred_time"):
                try:
                    mark(134.1 if int(answers["preferred_time"].split(":")[0]) < 12 else 195.6, 588.2)
                except ValueError:
                    pass
            if kind == "medical":
                select("clinic_service", MEDICAL_SERVICES, [
                    (76.8, 556.8), (76.8, 543.2), (76.8, 529.8), (76.8, 516.2),
                    (334.6, 556.8), (334.6, 543.2), (334.6, 529.8),
                ])
                field("clinic_other", 337, 516.6, 204)
                multi_field("complaint", [(182, 472.5, 358), (57, 457.5, 484)], "Chief complaint")
                for key, x, y, width in [
                    ("duration", 142, 442.5, 398),
                    ("allergies", 183, 427.5, 358),
                    ("medications", 135, 412.5, 406),
                    ("condition_other", 57, 384.0, 484),
                ]:
                    field(key, x, y, width)
                select("conditions", ("Asthma", "Hypertension", "Diabetes", "Heart disease", "Other"), [
                    (159.6, 396.1), (207.9, 396.1), (276.7, 396.1), (329.6, 396.1), (400.7, 396.1),
                ])
                write("Date filed", filed, 416, 321.5, 160, align="center")
                appendix_y = 200
            else:
                select("clinic_service", DENTAL_SERVICES, [
                    (76.8, 547.6), (76.8, 534.1), (76.8, 520.6), (76.8, 507.1),
                    (334.6, 547.6), (334.6, 534.1), (334.6, 520.6),
                ])
                field("clinic_other", 337, 507.5, 204)
                multi_field("complaint", [(179, 463.3, 361), (57, 448.3, 484)], "Chief complaint")
                for key, x, y, width in [
                    ("last_visit", 144, 433.3, 66),
                    ("pain", 288, 433.3, 252),
                    ("allergies", 231, 403.8, 310),
                    ("medications", 135, 388.8, 406),
                    ("condition_other", 57, 360.3, 484),
                ]:
                    field(key, x, y, width)
                select("symptoms", ("Toothache", "Swelling", "Bleeding gums", "Sensitivity", "None"), [
                    (138.2, 416.9), (197.4, 416.9), (248.5, 416.9), (323.2, 416.9), (380.6, 416.9),
                ])
                select("conditions", ("Hypertension", "Diabetes", "Heart disease", "Bleeding disorder", "Asthma", "Other"), [
                    (128.6, 372.4), (197.4, 372.4), (250.3, 372.4), (321.4, 372.4), (405.7, 372.4), (454.0, 372.4),
                ])
                write("Date filed", filed, 416, 297.8, 160, align="center")
                appendix_y = 178

    for key, value in answers.items():
        if key not in used and value and key not in {"schedule"}:
            label = key.replace("_", " ").capitalize()
            if isinstance(value, list):
                value = ", ".join(value)
            overflow.append((label, str(value)))

    if overflow:
        y = appendix_y
        _draw(canvas, 50, y, "Additional request details", 9.5, bold=True)
        y -= 14
        for label, value in overflow:
            lines = []
            for paragraph in f"{label}: {value}".splitlines():
                lines.extend(_wrap_for_width(paragraph, 9.0, 510))
            for line in lines:
                if y < 48:
                    footer()
                    canvas.showPage()
                    canvas.setFillColor(INK)
                    y = PAGE_HEIGHT - 48
                _draw(canvas, 50, y, line, 9.0)
                y -= 12
            y -= 3
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
