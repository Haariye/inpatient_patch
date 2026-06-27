# Copyright (c) 2026, Dagaar
"""
Workflow glue so the clinical sheets COMMUNICATE with the Inpatient Record and
gate one another.

  * When a sheet is created/submitted, update_stage() stamps the matching stage
    flag on its Inpatient Record and notifies the patient.
  * get_stage() returns the computed completion state (from real linked docs)
    that the Inpatient Record hub uses to decide which buttons/steps to show.
  * before_submit guards enforce ordering (e.g. cannot run the OT case until the
    Pre-Operative Checklist says READY FOR OR).
"""
import frappe
from frappe import _
from frappe.utils import cint

from inpatient_patch.inpatient_patch.notifications import notify_patient

# doctype -> (stage flag on Inpatient Record, friendly event, patient message)
STAGE_MAP = {
    "Emergency Assessment Sheet": ("custom_emergency_done", "Emergency Assessment",
        "Your emergency assessment has been recorded."),
    "Nursing Admission Assessment": ("custom_nursing_assessment_done", "Nursing Assessment",
        "A nurse has completed your admission assessment."),
    "History Clinical Examination": ("custom_history_exam_done", "Clinical Examination",
        "Your clinical examination has been completed."),
    "Pre Operative Checklist": ("custom_preop_ready", "Pre-Op Checklist",
        "Your pre-operative checklist is being prepared."),
    "Operation Procedure Note": ("custom_operated", "Operation Completed",
        "Your operation has been recorded."),
    "Discharge Summary": ("custom_discharge_ready", "Discharge",
        "Your discharge summary is ready."),
}


def update_stage(doc, method=None):
    try:
        ip = doc.get("inpatient_record")
        if not ip or not frappe.db.exists("Inpatient Record", ip):
            return
        flag_event = STAGE_MAP.get(doc.doctype)
        if not flag_event:
            # still notify for other sheets generically
            notify_patient(ip, doc.doctype, _("Update recorded: {0}.").format(doc.doctype),
                           ref_dt=doc.doctype, ref_dn=doc.name)
            return
        flag, event, msg = flag_event

        # Pre-Op checklist only counts when it is actually READY FOR OR
        if doc.doctype == "Pre Operative Checklist" and not cint(doc.get("ready_for_or")):
            return

        frappe.db.set_value("Inpatient Record", ip, flag, 1, update_modified=False)
        notify_patient(ip, event, msg, ref_dt=doc.doctype, ref_dn=doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "update_stage")


@frappe.whitelist()
def get_stage(inpatient_record):
    """Computed completion state from real linked documents (not just the
    convenience checkboxes), used to gate the hub UI."""
    def has(dt, extra=None):
        filt = {"inpatient_record": inpatient_record}
        if extra:
            filt.update(extra)
        try:
            return frappe.db.count(dt, filt) > 0
        except Exception:
            return False

    dept = frappe.db.get_value("Inpatient Record", inpatient_record,
                               "custom_medical_department")
    is_surgical = 0
    if dept:
        protocol = frappe.db.get_value("Department Admission Protocol",
                                       {"medical_department": dept, "enabled": 1}, "name")
        if protocol:
            is_surgical = cint(frappe.db.get_value(
                "Department Admission Protocol", protocol, "is_surgical"))

    stage = {
        "is_surgical": is_surgical,
        "has_emergency": has("Emergency Assessment Sheet"),
        "has_admission_data": has("Admission Social Data"),
        "has_nursing": has("Nursing Admission Assessment"),
        "has_history": has("History Clinical Examination"),
        "has_consent": has("Surgical Consent Form"),
        "preop_ready": has("Pre Operative Checklist", {"ready_for_or": 1}),
        "has_ot_case": has("Operation Theatre Case"),
        "operated": has("Operation Procedure Note") or
                    frappe.db.count("Operation Theatre Case",
                                    {"inpatient_record": inpatient_record,
                                     "status": "Completed"}) > 0,
        "has_recovery": has("Recovery Nurse Record"),
        "has_postop": has("Post Operative Checklist"),
        "discharged": has("Discharge Summary"),
    }
    return stage


def before_submit_ot_case(doc, method=None):
    """Cannot run the OT case until a Pre-Operative Checklist for this record is
    READY FOR OR (spec: no patient enters OR with an incomplete checklist)."""
    ready = frappe.db.count("Pre Operative Checklist",
                            {"inpatient_record": doc.inpatient_record,
                             "ready_for_or": 1})
    if not ready:
        frappe.throw(_("Cannot proceed: complete a <b>Pre-Operative Checklist</b> "
                       "and ensure 'READY FOR OPERATING ROOM' is ticked first."))


def before_submit_discharge(doc, method=None):
    """Light gating: a clinical baseline (History & Examination) must exist."""
    if not frappe.db.count("History Clinical Examination",
                           {"inpatient_record": doc.inpatient_record}):
        frappe.throw(_("Cannot discharge: a <b>History & Clinical Examination</b> "
                       "must be completed for this admission."))
