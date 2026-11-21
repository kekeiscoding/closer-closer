from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


MANILA = ZoneInfo("Asia/Manila")
UNIT_PRICE = 5_000

REGISTRAR = {
    "tor": "Transcript of Records",
    "diploma": "Diploma",
    "good-moral": "Good Moral",
    "graduation": "Certification of Graduation",
    "grades": "Certification of Grades",
    "units": "Certification of Units Earned",
    "enrollment": "Certification of Enrollment",
    "authentication": "DFA/CHED Authentication of Student’s Records",
    "others": "Others (Specify)",
}

OSAS = {
    "id-lanyard": (
        "ID and Lanyard Issuance and Replacement",
        "Apply for a new ID or lanyard, or request a replacement or update.",
        "badge",
        "OSAS-QF-01",
    ),
    "medical": (
        "Medical Appointment",
        "Request a preferred time to visit the University Clinic.",
        "medical",
        "OSAS-QF-02",
    ),
    "dental": (
        "Dental Appointment",
        "Request a check-up, consultation, or treatment at the Dental Clinic.",
        "dental",
        "OSAS-QF-03",
    ),
}


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"
    required: bool = False
    options: tuple = ()
    wide: bool = False
    hint: str = ""


def F(name, label, kind="text", required=False, *, options=(), wide=False, hint=""):
    return Field(name, label, kind, required, options, wide, hint)


def contact():
    return (
        F("phone", "Mobile number", "tel", True),
        F("email", "Email address", "email", True),
    )


TERMS = ("First semester", "Second semester", "Summer term")

REGISTRAR_DETAILS = (
    ("Applicant information", (
        F("middle_initial", "Middle initial"),
        F("maiden_name", "Maiden name", hint="Surname used upon entry, if applicable."),
        F("entry_from", "Entry year from", "year", True),
        F("entry_to", "Entry year to", "year", True),
        F("graduation_date", "Date of graduation", "date"),
    )),
    ("Contact details", (
        F("address", "Permanent address", "textarea", True, wide=True),
        *contact(),
        F("direct_line", "Direct line", "tel"),
        F("fax", "Fax number", "tel"),
    )),
    ("Purpose", (
        F("tor_purpose", "Purpose of Transcript of Records", "select", options=(
            "Evaluation", "Employment / Promotion", "For further studies"
        )),
        F("further_studies", "College or university"),
        F("purpose", "Purpose of other documents", "textarea", wide=True),
    )),
)

GRADE_FIELDS = (
    F("grade_from_year", "Start academic year", "school_year", hint="Example 2024–2025"),
    F("grade_from_sem", "Start semester", "select", options=TERMS),
    F("grade_to_year", "End academic year", "school_year", hint="Example 2025–2026"),
    F("grade_to_sem", "End semester", "select", options=TERMS),
)

ID_SERVICE = (
    "First-time issuance (new student)", "Replacement of ID",
    "Re-validation / updating of ID", "Change of information",
)
LANYARD_SERVICE = ("Issuance of lanyard", "Replacement of lanyard")
ID_REASONS = ("Lost", "Damaged / defective", "Stolen", "Change of personal information", "Other")

ID_FIELDS = (
    ("Applicant information", (F("middle_name", "Middle name"), *contact())),
    ("Request details", (
        F("id_service", "ID", "select", options=ID_SERVICE),
        F("lanyard_service", "Lanyard", "select", options=LANYARD_SERVICE),
        F("replacement_reason", "Reason for replacement", "select", options=ID_REASONS),
        F("replacement_other", "Other reason"),
    )),
    ("Requirements", (
        F("requirements", "Items submitted", "checks", options=(
            "Certificate of Registration / proof of enrollment",
            "Affidavit of Loss (lost or stolen ID)",
            "Police report (stolen ID)",
            "Damaged ID / lanyard for surrender",
            "Recent 1×1 or 2×2 ID photo with name tag",
            "Official receipt of payment (for replacement)",
        ), wide=True),
    )),
)

PATIENT_FIELDS = (
    F("middle_name", "Middle name"),
    F("sex", "Sex", "select", True, options=("Female", "Male", "Intersex", "Prefer not to say")),
    F("birth_date", "Date of birth", "date", True),
    *contact(),
    F("emergency_name", "Emergency contact person", "text", True),
    F("emergency_phone", "Emergency contact number", "tel", True),
)
APPOINTMENT_FIELDS = (
    F("preferred_date", "Preferred date", "date", True),
    F("preferred_time", "Preferred time", "time", True),
)
HEALTH_COMMON = (
    F("allergies", "Known allergies", hint="Enter any relevant allergies."),
    F("medications", "Current medications"),
)
MEDICAL_SERVICES = (
    "General medical consultation", "Physical examination", "Medical certificate / clearance",
    "Follow-up check-up", "Blood pressure / vital signs check", "Wound care / first aid", "Other",
)
DENTAL_SERVICES = (
    "Oral examination / check-up", "Oral prophylaxis (cleaning)", "Tooth extraction",
    "Tooth filling", "Dental consultation", "Dental certificate / clearance", "Other",
)
MEDICAL_FIELDS = (
    ("Patient information", PATIENT_FIELDS),
    ("Appointment details", APPOINTMENT_FIELDS),
    ("Type of consultation", (
        F("clinic_service", "Service requested", "checks", True, options=MEDICAL_SERVICES, wide=True),
        F("clinic_other", "Other service", wide=True),
    )),
    ("Health information", (
        F("complaint", "Reason for visit or chief complaint", "textarea", True, wide=True),
        F("duration", "Duration of symptoms"),
        *HEALTH_COMMON,
        F("conditions", "Existing medical conditions", "checks",
          options=("Asthma", "Hypertension", "Diabetes", "Heart disease", "Other"), wide=True),
        F("condition_other", "Other medical condition", wide=True),
    )),
)
DENTAL_FIELDS = (
    ("Patient information", PATIENT_FIELDS),
    ("Appointment details", APPOINTMENT_FIELDS),
    ("Dental service", (
        F("clinic_service", "Service requested", "checks", True, options=DENTAL_SERVICES, wide=True),
        F("clinic_other", "Other service", wide=True),
    )),
    ("Dental and health history", (
        F("complaint", "Reason for visit or chief complaint", "textarea", True, wide=True),
        F("last_visit", "Date of last dental visit", "date"),
        F("pain", "Pain level (0–10)", "pain"),
        F("symptoms", "Current symptoms", "checks",
          options=("Toothache", "Swelling", "Bleeding gums", "Sensitivity", "None"), wide=True),
        *HEALTH_COMMON,
        F("conditions", "Existing medical conditions", "checks", options=(
            "Hypertension", "Diabetes", "Heart disease", "Bleeding disorder", "Asthma", "Other",
        ), wide=True),
        F("condition_other", "Other medical condition", wide=True),
    )),
)

OSAS_FIELDS = {"id-lanyard": ID_FIELDS, "medical": MEDICAL_FIELDS, "dental": DENTAL_FIELDS}

DECLARATIONS = {
    "registrar": "I certify that the information provided in this request is true and correct.",
    "id-lanyard": (
        "I certify that the information provided is true and correct. I understand that my ID "
        "is non-transferable and that I am responsible for its proper use."
    ),
    "medical": (
        "I certify that the information provided is true and correct and consent to examination "
        "and treatment by University Clinic personnel. I understand that my records are confidential."
    ),
    "dental": (
        "I certify that the information provided is true and correct and consent to dental examination "
        "and treatment by University Dental Clinic personnel. I understand that my records are confidential."
    ),
}

CLINIC_GUIDANCE = {
    "medical": "Bring your school ID. In an emergency, proceed directly to the University Clinic.",
    "dental": "Bring your school ID. In a dental emergency, proceed directly to the University Dental Clinic.",
}


def collect(form, groups, errors):
    answers = {}
    for _, fields in groups:
        for field in fields:
            value = form.get(field.name, "").strip()
            if field.kind == "checks":
                submitted = form.getlist(field.name)
                value = [option for option in field.options if option in submitted]
                if set(submitted) - set(field.options):
                    errors[field.name] = f"Choose a listed option for {field.label.lower()}."
            answers[field.name] = value
            if not value:
                if field.required and field.name not in errors:
                    errors[field.name] = f"Enter {field.label.lower()}."
                continue
            if field.kind == "select" and value not in field.options:
                errors[field.name] = f"Choose a listed option for {field.label.lower()}."
            if field.kind not in {"checks", "select"}:
                validate_scalar(field, value, errors)
    return answers


def validate_scalar(field, value, errors):
    label = field.label.lower()
    if len(value) > (1800 if field.kind == "textarea" else 200):
        errors[field.name] = f"Shorten {label}."
        return
    try:
        if field.kind == "date":
            date.fromisoformat(value)
        elif field.kind == "time":
            time.fromisoformat(value)
        elif field.kind in {"year", "age", "pain"}:
            low, high = {"year": (1900, 2200), "age": (0, 120), "pain": (0, 10)}[field.kind]
            if not low <= int(value) <= high:
                raise ValueError
        elif field.kind == "email":
            local, domain = value.split("@")
            if not local or "." not in domain or any(ch.isspace() for ch in value):
                raise ValueError
        elif field.kind == "tel" and not any(ch.isdigit() for ch in value):
            raise ValueError
    except ValueError:
        errors[field.name] = f"Enter a valid {label}."


def registrar_submission(form):
    errors = {}
    items = []
    other_title = form.get("others", "").strip()
    for code, label in REGISTRAR.items():
        if code not in form.getlist("services"):
            continue
        try:
            quantity = int(form.get(f"copies_{code}", "1"))
            if not 1 <= quantity <= 20:
                raise ValueError
        except ValueError:
            errors[f"copies_{code}"] = "Enter 1 to 20 copies."
            continue
        items.append((code, other_title if code == "others" else label, quantity))
    selected = form.getlist("services")
    if not selected or set(selected) - REGISTRAR.keys():
        errors["services"] = "Select at least one listed document."
    answers = collect(form, REGISTRAR_DETAILS, errors)
    if "tor" in selected:
        if not answers["tor_purpose"]:
            errors["tor_purpose"] = "Choose the purpose of the transcript."
        if answers["tor_purpose"] == "For further studies" and not answers["further_studies"]:
            errors["further_studies"] = "Enter the college or university."
        if answers["tor_purpose"] != "For further studies":
            answers["further_studies"] = ""
    else:
        answers["tor_purpose"] = answers["further_studies"] = ""
    if any(code != "tor" for code in selected) and not answers["purpose"]:
        errors["purpose"] = "Enter the purpose of the other documents."
    if "others" in selected:
        answers["others"] = other_title
        if not 1 <= len(answers["others"]) <= 200:
            errors["others"] = "Specify the document in 1 to 200 characters."
    if "grades" in selected:
        answers.update(collect(form, (("Grade coverage", GRADE_FIELDS),), errors))
    check_academic_dates(answers, errors, "grades" in selected, datetime.now(MANILA).date())
    if form.get("consent") != "yes":
        errors["consent"] = "Confirm the declaration."
    return items, answers, errors


def check_academic_dates(answers, errors, with_grades, today):
    years = {}
    for key in ("entry_from", "entry_to"):
        if key in errors:
            continue
        try:
            year = int(answers.get(key, ""))
            if 1900 <= year <= today.year:
                years[key] = year
            else:
                errors[key] = f"Enter an attendance year from 1900 to {today.year}."
        except ValueError:
            errors[key] = "Enter a valid attendance year."
    first = years.get("entry_from")
    last = years.get("entry_to")
    if first and last and first > last:
        errors["entry_to"] = "The last attendance year must be on or after the first."
    graduation = None
    if answers.get("graduation_date") and "graduation_date" not in errors:
        try:
            graduation = date.fromisoformat(answers["graduation_date"])
            if graduation > today:
                errors["graduation_date"] = "Graduation must be today or earlier."
            elif first and graduation.year < first:
                errors["graduation_date"] = "Graduation cannot precede the first year of attendance."
            elif last and graduation.year < last:
                errors["graduation_date"] = "Graduation cannot precede the last year of attendance."
        except ValueError:
            errors["graduation_date"] = "Enter a valid graduation date."
    if not with_grades:
        return
    starts = grade_point(answers, "from", errors)
    ends = grade_point(answers, "to", errors)
    if starts and ends and starts > ends:
        errors["grade_to_sem"] = "End year and semester must be on or after the start."
    for edge, term_start in (("from", starts), ("to", ends)):
        if term_start is None:
            continue
        key = f"grade_{edge}_year"
        if term_start > today:
            errors[key] = "Select a grade period that has already started."
        elif graduation and term_start > graduation:
            errors[key] = "Grade coverage cannot extend past graduation."
        elif (first and term_start.year < first) or (last and term_start.year > last):
            errors[key] = "Select a grade period within the years you attended."


def grade_point(answers, edge, errors):
    year_key = f"grade_{edge}_year"
    term_key = f"grade_{edge}_sem"
    try:
        start, end = answers.get(year_key, "").replace("–", "-").split("-")
        start_year = int(start)
        if len(start) != 4 or len(end) != 4 or not (1900 <= start_year <= 2199):
            raise ValueError
        if int(end) != start_year + 1:
            raise ValueError
        answers[year_key] = f"{start_year}–{start_year + 1}"
    except ValueError:
        errors[year_key] = "Enter an academic year such as 2024–2025."
        return None
    term = answers.get(term_key)
    if term not in TERMS:
        errors[term_key] = "Choose a semester."
        return None
    # Use the start month of each term to compare against calendar dates.
    if term == TERMS[0]:
        return date(start_year, 8, 1)
    return date(start_year + 1, 1 if term == TERMS[1] else 6, 1)


def osas_submission(service, form):
    errors = {}
    answers = collect(form, OSAS_FIELDS[service], errors)
    if service == "id-lanyard":
        if not (answers["id_service"] or answers["lanyard_service"]):
            errors["id_service"] = "Select an ID or lanyard service."
        replacement = "Replacement of ID" == answers["id_service"] or (
            "Replacement of lanyard" == answers["lanyard_service"]
        )
        if replacement and not answers["replacement_reason"]:
            errors["replacement_reason"] = "Choose a reason for replacement."
        if answers["replacement_reason"] == "Other" and not answers["replacement_other"]:
            errors["replacement_other"] = "Enter the other reason."
    else:
        today = datetime.now(MANILA).date()
        if answers["preferred_date"] and "preferred_date" not in errors:
            if date.fromisoformat(answers["preferred_date"]) < today:
                errors["preferred_date"] = "Choose today or a later date."
        if answers["birth_date"] and "birth_date" not in errors:
            birth = date.fromisoformat(answers["birth_date"])
            if birth > today:
                errors["birth_date"] = "Enter a date of birth in the past."
            else:
                birthday_passed = (today.month, today.day) >= (birth.month, birth.day)
                answers["age"] = str(today.year - birth.year - (not birthday_passed))
        if "Other" in answers["clinic_service"] and not answers["clinic_other"]:
            errors["clinic_other"] = "Enter the other service."
        if "Other" in answers["conditions"] and not answers["condition_other"]:
            errors["condition_other"] = "Enter the other condition."
        if "None" in answers.get("symptoms", []) and len(answers["symptoms"]) > 1:
            errors["symptoms"] = "Choose either None or your current symptoms."
        if answers.get("last_visit") and "last_visit" not in errors:
            if date.fromisoformat(answers["last_visit"]) > today:
                errors["last_visit"] = "Enter today or an earlier date."
    if form.get("consent") != "yes":
        errors["consent"] = "Confirm the declaration."
    return [(service, OSAS[service][0], 1)], answers, errors


def response_groups(office, items, answers):
    if office == "OSAS":
        service = items[0]["service"]
        groups = OSAS_FIELDS[service]
        if service in CLINIC_GUIDANCE:
            title, fields = groups[0]
            return ((title, fields + (F("age", "Age at filing"),)),) + groups[1:]
        return groups
    groups = list(REGISTRAR_DETAILS)
    if any(item["service"] == "grades" for item in items):
        groups.append(("Grade coverage", GRADE_FIELDS))
    if "others" in answers:
        groups.append(("Other document", (F("others", "Document requested"),)))
    return groups
