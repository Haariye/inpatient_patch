# Copyright (c) 2026, Dagaar
"""Nurse Handover Board - a self-contained shift whiteboard.

One active board per service-unit + shift + date. Each patient is one row whose
summary is ABSORBED from the doctypes the nurse uses during the shift
(Medication Administration Record, Progress Note, Doctor Order, Daily Round Plan,
Diabetic Insulin Chart, Vital Signs). There is no separate handover form.
"""
import frappe
from frappe import _
from frappe.utils import nowdate, now_datetime, cint, add_days


def _has(dt):
    return bool(frappe.db.exists("DocType", dt))


def _latest(dt, ir, fields, order="modified desc"):
    if not _has(dt):
        return None
    try:
        rows = frappe.get_all(dt, filters={"inpatient_record": ir, "docstatus": ["!=", 2]},
                              fields=fields, order_by=order, limit=1)
        return rows[0] if rows else None
    except Exception:
        return None


def _count(dt, ir, extra=None):
    if not _has(dt):
        return 0
    flt = {"inpatient_record": ir, "docstatus": ["!=", 2]}
    if extra:
        flt.update(extra)
    try:
        return frappe.db.count(dt, flt)
    except Exception:
        return 0


def _summary_for(ir):
    """Absorb the latest picture for one inpatient record from the nurse doctypes."""
    s = {"meds_given_count": 0, "pending_meds_count": 0, "pending_tasks_count": 0,
         "latest_vitals": "", "latest_glucose": "", "latest_progress": "",
         "pending_orders": "", "round_plan": "", "meds_summary": "", "alerts_summary": ""}

    # Medication Administration Record - given vs pending
    if _has("Medication Administration Record"):
        s["meds_given_count"] = _count("Medication Administration Record", ir, {"given": 1}) \
            if frappe.get_meta("Medication Administration Record").has_field("given") else \
            _count("Medication Administration Record", ir)
        total_mar = _count("Medication Administration Record", ir)
        s["pending_meds_count"] = max(total_mar - s["meds_given_count"], 0)
        mrow = _latest("Medication Administration Record", ir,
                       ["name", "modified"])
        if mrow:
            s["meds_summary"] = "Last MAR: {0}".format(mrow.get("name"))

    # Doctor Order - pending orders/tasks
    s["pending_tasks_count"] = _count("Doctor Order", ir)
    dorow = _latest("Doctor Order", ir, ["name"])
    if dorow:
        s["pending_orders"] = dorow.get("name")

    # Progress Note - latest text
    for fld in ("note", "progress_note", "clinical_note", "summary"):
        pr = _latest("Progress Note", ir, ["name", fld]) if _has("Progress Note") else None
        if pr and pr.get(fld):
            s["latest_progress"] = (pr.get(fld) or "")[:200]
            break

    # Daily Round Plan
    rp = _latest("Daily Round Plan", ir, ["name"]) if _has("Daily Round Plan") else None
    if rp:
        s["round_plan"] = rp.get("name")

    # Diabetic Insulin Chart - latest glucose / insulin
    if _has("Diabetic Insulin Chart"):
        for gf, inf in (("blood_glucose", "insulin_dose"), ("glucose", "insulin"),
                        ("rbs", "dose")):
            di = _latest("Diabetic Insulin Chart", ir, ["name", gf, inf])
            if di and (di.get(gf) or di.get(inf)):
                s["latest_glucose"] = "{0} / {1}".format(di.get(gf) or "-", di.get(inf) or "-")
                break

    # Vitals - try Vital Signs then any vitals-bearing doctype
    for vdt, bp, pulse, temp in (("Vital Signs", "bp", "pulse", "temperature"),):
        v = _latest(vdt, ir, ["name", bp, pulse, temp]) if _has(vdt) else None
        if v:
            s["latest_vitals"] = "BP {0} | HR {1} | T {2}".format(
                v.get(bp) or "-", v.get(pulse) or "-", v.get(temp) or "-")
            break

    # Alerts - allergies from the Inpatient Record
    allergies = frappe.db.get_value("Inpatient Record", ir, "custom_allergies") \
        if frappe.get_meta("Inpatient Record").has_field("custom_allergies") else None
    if allergies:
        s["alerts_summary"] = allergies
    return s


def _admitted_in_ward(ward):
    recs = frappe.get_all("Inpatient Record", filters={"status": "Admitted"},
        fields=["name", "patient", "patient_name", "custom_current_bed"])
    out = []
    for r in recs:
        if not ward or r.custom_current_bed == ward or _bed_in_ward(r.custom_current_bed, ward):
            out.append(r)
    return out


def _board_patients(doc):
    """Whose patients this board covers: by Responsible Nurse first, then ward,
    then all admitted."""
    if doc.get("responsible_nurse"):
        return frappe.get_all("Inpatient Record",
            filters={"status": "Admitted", "custom_responsible_nurse": doc.responsible_nurse},
            fields=["name", "patient", "patient_name", "custom_current_bed"])
    return _admitted_in_ward(doc.get("ward"))


def _bed_in_ward(bed, ward):
    if not bed:
        return False
    return frappe.db.get_value("Healthcare Service Unit", bed,
                               "parent_healthcare_service_unit") == ward


def _fill_row(row, r):
    s = _summary_for(r["name"] if isinstance(r, dict) else r.name)
    ir = r["name"] if isinstance(r, dict) else r.name
    row.inpatient_record = ir
    row.patient = r.get("patient")
    row.patient_name = r.get("patient_name")
    row.bed_no = r.get("custom_current_bed")
    for k, v in s.items():
        if row.meta.has_field(k) or True:
            try:
                row.set(k, v)
            except Exception:
                pass
    return s


@frappe.whitelist()
def generate_shift_board(board):
    doc = frappe.get_doc("Nurse Handover Board", board)
    doc.set("patients", [])
    admitted = _board_patients(doc)
    meds = tasks = 0
    for r in admitted:
        row = doc.append("patients", {})
        s = _fill_row(row, r)
        row.handover_status = "Pending"
        meds += cint(s["pending_meds_count"])
        tasks += cint(s["pending_tasks_count"])
    doc.total_patients = len(admitted)
    doc.pending_meds_count = meds
    doc.pending_tasks_count = tasks
    doc.completed_count = 0
    doc.last_updated = now_datetime()
    doc.save(ignore_permissions=True)
    frappe.msgprint(_("Board generated for {0} patient(s), data absorbed from the "
                      "nurse's charts.").format(len(admitted)))
    return doc.name


@frappe.whitelist()
def pull_latest_data(board):
    doc = frappe.get_doc("Nurse Handover Board", board)
    meds = tasks = done = 0
    for row in doc.patients:
        s = _summary_for(row.inpatient_record)
        for k, v in s.items():
            try:
                row.set(k, v)
            except Exception:
                pass
        if row.handover_status == "Accepted":
            done += 1
        meds += cint(s["pending_meds_count"])
        tasks += cint(s["pending_tasks_count"])
    doc.pending_meds_count = meds
    doc.pending_tasks_count = tasks
    doc.completed_count = done
    doc.last_updated = now_datetime()
    doc.save(ignore_permissions=True)
    frappe.msgprint(_("Latest data pulled."))
    return doc.name


@frappe.whitelist()
def wrap_shift(board):
    doc = frappe.get_doc("Nurse Handover Board", board)
    if doc.status != "Open":
        frappe.throw(_("Only an Open board can be wrapped."))
    order = ["Morning", "Afternoon", "Night"]
    idx = order.index(doc.shift) if doc.shift in order else 0
    next_shift = order[(idx + 1) % 3]
    next_date = doc.handover_date if idx < 2 else add_days(doc.handover_date, 1)
    if _active_board(doc.ward, next_shift, next_date):
        frappe.throw(_("An active board already exists for {0} / {1} / {2}.")
                     .format(doc.ward, next_shift, next_date))
    nb = frappe.new_doc("Nurse Handover Board")
    nb.ward = doc.ward
    nb.shift = next_shift
    nb.handover_date = next_date
    nb.from_nurse = doc.to_nurse
    nb.status = "Open"
    for row in doc.patients:
        if (cint(row.pending_meds_count) or cint(row.pending_tasks_count)
                or row.handover_status != "Accepted"):
            nb.append("patients", {
                "inpatient_record": row.inpatient_record, "patient": row.patient,
                "patient_name": row.patient_name, "bed_no": row.bed_no,
                "condition": row.condition, "alerts_summary": row.alerts_summary,
                "nurse_notes": row.nurse_notes, "handover_status": "Pending",
            })
    nb.total_patients = len(nb.patients)
    nb.last_updated = now_datetime()
    nb.flags.ignore_mandatory = True
    nb.insert(ignore_permissions=True)
    # refresh the carried-forward rows with live data
    pull_latest_data(nb.name)
    doc.status = "Wrapped"
    doc.last_updated = now_datetime()
    doc.save(ignore_permissions=True)
    frappe.msgprint(_("Shift wrapped. Next board created: {0}").format(nb.name))
    return nb.name


@frappe.whitelist()
def accept_handover(board):
    doc = frappe.get_doc("Nurse Handover Board", board)
    doc.status = "Accepted"
    for row in doc.patients:
        row.handover_status = "Accepted"
    doc.completed_count = len(doc.patients)
    doc.last_updated = now_datetime()
    doc.save(ignore_permissions=True)
    return doc.name


def _active_board(ward, shift, date):
    return frappe.db.exists("Nurse Handover Board", {
        "ward": ward, "shift": shift, "handover_date": date,
        "status": ["in", ["Open", "Wrapped"]]})


def guard_duplicate_board(doc, method=None):
    if doc.status not in ("Open", "Wrapped"):
        return
    dup = frappe.db.get_value("Nurse Handover Board", {
        "ward": doc.ward, "shift": doc.shift, "handover_date": doc.handover_date,
        "status": ["in", ["Open", "Wrapped"]], "name": ["!=", doc.name or ""]})
    if dup:
        frappe.throw(_("An active board {0} already exists for this service unit, "
                       "shift and date.").format(dup))


# ---- Nurse Admission Assignment -------------------------------------------
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
        doc.db_set("vital_signs", vs.name, update_modified=False)
        doc.db_set("vs_created", 1, update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "create_vitals_from_mar")


@frappe.whitelist()
def patient_shift_detail(inpatient_record):
    """Rich data for one patient on the handover board: medicines given this shift,
    a vitals series, and a glucose series. Defensive on field names."""
    out = {"meds": [], "vitals": [], "glucose": []}

    # --- medicines given (from MAR entries) ---
    mars = frappe.get_all("Medication Administration Record",
        filters={"inpatient_record": inpatient_record, "docstatus": ["!=", 2]},
        fields=["name"], order_by="modified desc", limit=5)
    for m in mars:
        try:
            doc = frappe.get_doc("Medication Administration Record", m.name)
            for e in (doc.get("entries") or []):
                out["meds"].append({
                    "drug": e.get("drug") or e.get("drug_code") or e.get("medication") or "",
                    "dose": e.get("dose") or e.get("dosage") or "",
                    "time": str(e.get("time_given") or e.get("given_at") or ""),
                    "nurse": e.get("nurse") or e.get("given_by") or "",
                    "given": 1 if e.get("given") else 0,
                })
        except Exception:
            pass

    # --- vitals series (Vital Signs) ---
    if frappe.db.exists("DocType", "Vital Signs"):
        vmeta = frappe.get_meta("Vital Signs")
        fields = ["name"]
        for f in ("signs_date", "signs_time", "pulse", "temperature",
                  "respiratory_rate", "bp_systolic", "bp_diastolic",
                  "oxygen_saturation"):
            if vmeta.has_field(f):
                fields.append(f)
        try:
            vs = frappe.get_all("Vital Signs",
                filters={"inpatient_record": inpatient_record} if vmeta.has_field("inpatient_record")
                else {"patient": frappe.db.get_value("Inpatient Record", inpatient_record, "patient")},
                fields=fields, order_by="creation asc", limit=20)
            out["vitals"] = vs
        except Exception:
            pass

    # --- glucose series (Diabetic Insulin Chart entries) ---
    if frappe.db.exists("DocType", "Diabetic Insulin Chart"):
        charts = frappe.get_all("Diabetic Insulin Chart",
            filters={"inpatient_record": inpatient_record, "docstatus": ["!=", 2]},
            fields=["name"], order_by="modified desc", limit=5)
        for c in charts:
            try:
                doc = frappe.get_doc("Diabetic Insulin Chart", c.name)
                for e in (doc.get("entries") or []):
                    g = e.get("blood_glucose") or e.get("glucose") or e.get("rbs")
                    if g:
                        out["glucose"].append({
                            "time": str(e.get("reading_time") or e.get("time") or ""),
                            "glucose": g,
                            "insulin": e.get("insulin_dose") or e.get("insulin") or e.get("dose") or "",
                        })
            except Exception:
                pass
    return out
