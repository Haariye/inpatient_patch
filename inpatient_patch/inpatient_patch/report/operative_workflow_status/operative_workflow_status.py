# Copyright (c) 2026, Dagaar
"""Operative workflow status: every surgical admission with its checklist
completion across the PRE-OPERATIVE, INTRA-OPERATIVE and POST-OPERATIVE phases,
plus the patient's current stage. Sorted so the closest-to-theatre come first."""
import frappe
from frappe.utils import cint

STAGE_ORDER = {"Pre-Operative": 0, "Intra-Operative": 1, "Post-Operative": 2,
               "Discharged": 3}


def _yn(v):
    return "✓" if v else "—"


def execute(filters=None):
    columns = [
        {"label": "Patient", "fieldname": "patient_name", "fieldtype": "Data", "width": 160},
        {"label": "Inpatient Record", "fieldname": "inpatient_record",
         "fieldtype": "Link", "options": "Inpatient Record", "width": 150},
        {"label": "Current Stage", "fieldname": "stage", "fieldtype": "Data", "width": 130},
        {"label": "PRE: History", "fieldname": "pre_history", "fieldtype": "Data", "width": 95},
        {"label": "PRE: Consent", "fieldname": "pre_consent", "fieldtype": "Data", "width": 100},
        {"label": "PRE: Checklist Ready", "fieldname": "pre_ready", "fieldtype": "Data", "width": 130},
        {"label": "INTRA: Safety", "fieldname": "intra_safety", "fieldtype": "Data", "width": 100},
        {"label": "INTRA: Procedure Note", "fieldname": "intra_note", "fieldtype": "Data", "width": 140},
        {"label": "POST: Recovery", "fieldname": "post_recovery", "fieldtype": "Data", "width": 110},
        {"label": "POST: Post-Op Checklist", "fieldname": "post_checklist", "fieldtype": "Data", "width": 150},
    ]

    conditions = {"custom_is_surgical": 1}
    if filters and filters.get("inpatient_record"):
        conditions["name"] = filters["inpatient_record"]

    records = frappe.get_all("Inpatient Record", filters=conditions,
                             fields=["name", "patient_name"])
    rows = []
    for r in records:
        ip = r["name"]
        def has(dt, extra=None):
            f = {"inpatient_record": ip}
            if extra:
                f.update(extra)
            try:
                return frappe.db.count(dt, f) > 0
            except Exception:
                return False

        pre_history = has("History Clinical Examination")
        pre_consent = has("Surgical Consent Form")
        pre_ready = has("Pre Operative Checklist", {"ready_for_or": 1})
        intra_safety = has("Surgical Safety Checklist")
        intra_note = has("Operation Procedure Note")
        post_recovery = has("Recovery Nurse Record")
        post_checklist = has("Post Operative Checklist")
        discharged = has("Discharge Summary")

        if discharged:
            stage = "Discharged"
        elif post_recovery or post_checklist:
            stage = "Post-Operative"
        elif intra_note or intra_safety:
            stage = "Intra-Operative"
        else:
            stage = "Pre-Operative"

        rows.append({
            "patient_name": r["patient_name"], "inpatient_record": ip, "stage": stage,
            "_order": STAGE_ORDER.get(stage, 9),
            "pre_history": _yn(pre_history), "pre_consent": _yn(pre_consent),
            "pre_ready": _yn(pre_ready), "intra_safety": _yn(intra_safety),
            "intra_note": _yn(intra_note), "post_recovery": _yn(post_recovery),
            "post_checklist": _yn(post_checklist),
        })

    rows.sort(key=lambda x: x["_order"])
    return columns, rows
