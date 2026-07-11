# Copyright (c) 2026, Dagaar
"""Nurse handover helpers: permissions, session nurse, MAR vitals, patient detail.

Shared functions used by the Nurse Handover dashboard, the nurse row-level
permission rules, the Nurse Admission Assignment, and the MAR vitals capture.
Data is read from the doctypes the nurse already fills (Medication Administration
Record, Progress Note, Doctor Order, Daily Round Plan, Diabetic Insulin Chart,
Vital Signs).
"""
import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime, cint, add_days


@frappe.whitelist()
def load_admitted_patients(assignment):
    """Fill the assignment with every currently-admitted patient."""
    doc = frappe.get_doc("Nurse Admission Assignment", assignment)
    existing = {r.inpatient_record for r in doc.assignments}
    recs = frappe.get_all("Inpatient Record", filters={"status": "Admitted"},
        fields=["name", "patient_name", "custom_current_bed", "custom_responsible_nurse"])
    for r in recs:
        if doc.ward:
            bed = r.custom_current_bed
            if not (bed == doc.ward or frappe.db.get_value(
                    "Healthcare Service Unit", bed, "parent_healthcare_service_unit") == doc.ward):
                continue
        if r.name in existing:
            continue
        doc.append("assignments", {
            "inpatient_record": r.name, "patient_name": r.patient_name,
            "bed_no": r.custom_current_bed,
            "responsible_nurse": r.custom_responsible_nurse, "shift": doc.shift})
    doc.save(ignore_permissions=True)
    return doc.name


def push_assignments_to_records(doc, method=None):
    """On save, write each row's responsible nurse onto its Inpatient Record."""
    for row in doc.get("assignments") or []:
        if row.inpatient_record and row.responsible_nurse:
            frappe.db.set_value("Inpatient Record", row.inpatient_record,
                                "custom_responsible_nurse", row.responsible_nurse,
                                update_modified=False)


def get_session_nurse():
    """The Nurse linked to the logged-in user (or None)."""
    return frappe.db.get_value("Nurse", {"linked_user": frappe.session.user}, "name")


_PERM_OVERRIDE = {"System Manager", "Administrator", "Healthcare Administrator",
                  "Physician", "Medical Administrator", "Nursing Master Manager"}


def _nurse_restricted(user):
    """Return the Nurse name to restrict to, or None if this user is unrestricted."""
    roles = set(frappe.get_roles(user))
    if roles & _PERM_OVERRIDE:
        return None
    if "Nurse" not in roles:
        return None  # doctors, reception, etc. keep their normal access
    return frappe.db.get_value("Nurse", {"linked_user": user}, "name") or "__none__"


def ip_permission_query(user=None):
    """List-view filter: a Nurse only sees Inpatient Records assigned to her."""
    user = user or frappe.session.user
    nurse = _nurse_restricted(user)
    if nurse is None:
        return ""
    if nurse == "__none__":
        return "1=0"
    return "`tabInpatient Record`.custom_responsible_nurse = {0}".format(
        frappe.db.escape(nurse))


def ip_has_permission(doc, ptype=None, user=None):
    """Form-level check mirroring the list filter."""
    user = user or frappe.session.user
    nurse = _nurse_restricted(user)
    if nurse is None:
        return True
    if nurse == "__none__":
        return False
    return (doc.get("custom_responsible_nurse") or None) == nurse


@frappe.whitelist()
def session_nurse_and_shift():
    """Return {nurse, shift} for the logged-in nurse (for form defaults)."""
    nurse = get_session_nurse()
    shift = frappe.db.get_value("Nurse", nurse, "default_shift") if nurse else None
    return {"nurse": nurse, "shift": shift}


def create_vitals_from_mar(doc, method=None):
    """When a MAR is saved with vitals filled, create a Vital Signs record once.
    Field names are set defensively so it works across healthcare forks."""
    if cint(doc.get("vs_created")) or doc.get("vital_signs"):
        return
    vs_map = {
        "bp_systolic": doc.get("vs_bp_systolic"),
        "bp_diastolic": doc.get("vs_bp_diastolic"),
        "pulse": doc.get("vs_pulse"),
        "temperature": doc.get("vs_temperature"),
        "respiratory_rate": doc.get("vs_respiratory_rate"),
        "oxygen_saturation": doc.get("vs_spo2"),
        "spo2": doc.get("vs_spo2"),
    }
    if not any(v not in (None, "", 0) for v in vs_map.values()):
        return
    if not frappe.db.exists("DocType", "Vital Signs"):
        return
    try:
        vs = frappe.new_doc("Vital Signs")
        meta = vs.meta
        vs.patient = doc.get("patient")
        if meta.has_field("inpatient_record"):
            vs.inpatient_record = doc.get("inpatient_record")
        if meta.has_field("signs_date"):
            vs.signs_date = nowdate()
        if meta.has_field("signs_time"):
            vs.signs_time = frappe.utils.nowtime()
        for fld, val in vs_map.items():
            if val not in (None, "", 0) and meta.has_field(fld):
                vs.set(fld, val)
        vs.flags.ignore_mandatory = True
        vs.insert(ignore_permissions=True)
        # Vital Signs is submittable in healthcare - submit so it is not left draft
        try:
            if vs.meta.is_submittable:
                vs.submit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "submit vital signs")
        doc.db_set("vital_signs", vs.name, update_modified=False)
        doc.db_set("vs_created", 1, update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "create_vitals_from_mar")


@frappe.whitelist()
def patient_shift_detail(inpatient_record):
    """Rich data for the Nurse Handover dashboard: medicines (given / pending /
    discontinued), vitals series, glucose series, current bed, latest Daily Round
    Plan, progress notes and pending doctor orders."""
    out = {"meds": [], "vitals": [], "glucose": [], "bed": "",
           "round_plan": {}, "progress": [], "orders": []}

    ip = frappe.db.get_value("Inpatient Record", inpatient_record,
        ["patient", "custom_current_bed", "admission_service_unit"], as_dict=True) or {}
    out["bed"] = ip.get("custom_current_bed") or ip.get("admission_service_unit") or ""

    # --- medicines (MAR entries) ---
    for m in frappe.get_all("Medication Administration Record",
            filters={"inpatient_record": inpatient_record, "docstatus": ["!=", 2]},
            pluck="name", order_by="modified desc", limit=8):
        try:
            for e in (frappe.get_doc("Medication Administration Record", m).get("entries") or []):
                out["meds"].append({
                    "drug": e.get("drug_name") or e.get("drug_code") or "",
                    "dose": e.get("dose") or "",
                    "route": e.get("route") or "",
                    "time": str(e.get("administration_time") or e.get("scheduled_time") or ""),
                    "nurse": e.get("administered_by") or "",
                    "given": 1 if e.get("given") else 0,
                    "status": e.get("status") or ("Given" if e.get("given") else "Pending"),
                    "discontinued": 1 if (e.get("discontinued") or e.get("status") == "Discontinued") else 0,
                })
        except Exception:
            pass

    # --- vitals series (Vital Signs) ---
    if frappe.db.exists("DocType", "Vital Signs"):
        vmeta = frappe.get_meta("Vital Signs")
        fields = ["name"] + [f for f in ("signs_date", "signs_time", "pulse",
            "temperature", "respiratory_rate", "bp_systolic", "bp_diastolic",
            "oxygen_saturation") if vmeta.has_field(f)]
        try:
            flt = {"inpatient_record": inpatient_record} if vmeta.has_field("inpatient_record") \
                else {"patient": ip.get("patient")}
            out["vitals"] = frappe.get_all("Vital Signs", filters=flt,
                fields=fields, order_by="creation asc", limit=30)
        except Exception:
            pass

    # --- glucose series (Diabetic Insulin Chart -> Insulin Monitoring Entry) ---
    for c in frappe.get_all("Diabetic Insulin Chart",
            filters={"inpatient_record": inpatient_record, "docstatus": ["!=", 2]},
            pluck="name", order_by="modified desc", limit=8):
        try:
            for e in (frappe.get_doc("Diabetic Insulin Chart", c).get("entries") or []):
                g = e.get("rbs_mgdl") or e.get("blood_glucose") or e.get("glucose") or e.get("rbs")
                if g in (None, "", 0):
                    continue
                units = e.get("units") or e.get("insulin_dose") or ""
                kind = e.get("insulin_kind") or ""
                item = e.get("insulin_item") or ""
                insulin = ("{0} u {1}".format(units, ("- " + item) if item else "")).strip() if units else (item or "")
                out["glucose"].append({
                    "time": str(e.get("entry_datetime") or e.get("reading_time") or ""),
                    "glucose": g,
                    "meal": e.get("meal_relation") or e.get("shift") or "",
                    "insulin": (insulin + ((" (" + kind + ")") if kind else "")).strip(),
                })
        except Exception:
            pass
    # oldest-first for charting
    out["glucose"].sort(key=lambda x: x["time"])

    # --- latest Daily Round Plan (clinical daily info) ---
    rp = frappe.get_all("Daily Round Plan",
        filters={"inpatient_record": inpatient_record, "docstatus": ["!=", 2]},
        fields=["name"], order_by="modified desc", limit=1)
    if rp:
        try:
            d = frappe.get_doc("Daily Round Plan", rp[0].name)
            out["round_plan"] = {
                "name": d.name, "date": str(d.get("round_date") or ""),
                "condition": d.get("current_condition") or "",
                "diagnosis_update": d.get("diagnosis_update") or "",
                "treatment_plan": d.get("treatment_plan") or "",
                "medicine_changes": d.get("medicine_changes") or "",
                "lab_radiology_requests": d.get("lab_radiology_requests") or "",
                "discharge_plan": d.get("discharge_plan") or "",
                "follow_up_instructions": d.get("follow_up_instructions") or "",
                "round_plan": d.get("round_plan") or d.get("current_problems") or "",
            }
        except Exception:
            pass

    # --- progress notes (latest few) ---
    if frappe.db.exists("DocType", "Progress Note"):
        pmeta = frappe.get_meta("Progress Note")
        tf = next((f for f in ("note", "progress_note", "clinical_note", "summary", "notes")
                   if pmeta.has_field(f)), None)
        for p in frappe.get_all("Progress Note",
                filters={"inpatient_record": inpatient_record, "docstatus": ["!=", 2]},
                fields=["name", "modified"] + ([tf] if tf else []),
                order_by="modified desc", limit=4):
            out["progress"].append({"name": p.name, "when": str(p.get("modified"))[:16],
                                    "text": (p.get(tf) or "")[:300] if tf else ""})

    # --- pending doctor orders ---
    if frappe.db.exists("DocType", "Doctor Order"):
        for o in frappe.get_all("Doctor Order",
                filters={"inpatient_record": inpatient_record, "docstatus": ["!=", 2]},
                fields=["name", "modified"], order_by="modified desc", limit=6):
            out["orders"].append({"name": o.name, "when": str(o.get("modified"))[:16]})
    return out

