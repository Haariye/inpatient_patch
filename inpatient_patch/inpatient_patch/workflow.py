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
    care_type = frappe.db.get_value("Inpatient Record", inpatient_record,
                                    "custom_care_type")
    is_surgical = 1 if care_type == "Surgery" else 0
    if not care_type and dept:
        protocol = frappe.db.get_value("Department Admission Protocol",
                                       {"medical_department": dept, "enabled": 1}, "name")
        if protocol:
            is_surgical = cint(frappe.db.get_value(
                "Department Admission Protocol", protocol, "is_surgical"))

    stage = {
        "is_surgical": is_surgical,
        "has_emergency": has("Emergency Assessment Sheet"),
        "has_nursing": has("Nursing Admission Assessment"),
        "has_history": has("History Clinical Examination"),
        "has_consent": has("Surgical Consent Form"),
        "has_cardiac": has("Pre Operation Cardiac Review"),
        "has_preanesth": has("Pre Anesthetic Assessment"),
        "anesthesia_unfit": bool(frappe.get_all("Pre Anesthetic Assessment",
            filters={"inpatient_record": inpatient_record},
            or_filters=[["fitness", "like", "Unfit%"]], limit=1)),
        "cardiac_not_cleared": bool(frappe.db.sql(
            "select 1 from `tabPre Operation Cardiac Review` where inpatient_record=%s "
            "and ifnull(plan,'') not in ('','Fit for Surgery') limit 1", inpatient_record)),
        "has_preop": has("Pre Operative Checklist"),
        "preop_ready": has("Pre Operative Checklist", {"ready_for_or": 1}),
        "has_ot_case": has("Clinical Procedure"),
        "has_safety": has("Surgical Safety Checklist"),
        "has_ortb": False,
        "has_procnote": has("Operation Procedure Note"),
        "operated": has("Operation Procedure Note") or bool(frappe.db.sql(
            "select 1 from `tabClinical Procedure` where inpatient_record=%s "
            "and (custom_surgery_finish is not null or status='Completed') limit 1",
            inpatient_record)),
        "has_recovery": has("Recovery Nurse Record"),
        "has_postop": has("Post Operative Checklist"),
        "discharged": has("Discharge Summary"),
        "bed_billed": bool(frappe.db.exists("Sales Invoice", {
            "custom_inpatient_record": inpatient_record,
            "custom_is_inpatient_bed_invoice": 1})),
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
    from inpatient_patch.inpatient_patch.billing import discharge_block_reason, assert_no_draft_invoices
    assert_no_draft_invoices(doc.inpatient_record, step="discharge")
    reason = discharge_block_reason(doc.inpatient_record)
    if reason:
        frappe.throw(_(reason))


def create_discharge_followup(doc, method=None):
    """Create a follow-up Patient Appointment (healthcare handles fee validity)."""
    try:
        if not doc.get("follow_up_date") or doc.get("follow_up_appointment"):
            return
        practitioner = doc.get("follow_up_with") or frappe.db.get_value(
            "Inpatient Record", doc.inpatient_record, "primary_practitioner")
        if not practitioner:
            return
        appt = frappe.new_doc("Patient Appointment")
        appt.patient = doc.patient
        appt.practitioner = practitioner
        appt.appointment_date = doc.follow_up_date
        dept = frappe.db.get_value("Inpatient Record", doc.inpatient_record,
                                   "custom_medical_department")
        if dept and appt.meta.has_field("department"):
            appt.department = dept
        appt.flags.ignore_mandatory = True
        appt.insert(ignore_permissions=True)
        doc.db_set("follow_up_appointment", appt.name)
        notify_patient(doc.inpatient_record, "Follow-up Booked",
                       _("A follow-up appointment was booked for {0}.")
                       .format(doc.follow_up_date),
                       ref_dt="Patient Appointment", ref_dn=appt.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "create_discharge_followup")


def stamp_nursing_complete(doc, method=None):
    """When 'Nursing Completed' is ticked, stamp the completion time."""
    try:
        if doc.get("nursing_completed") and not doc.get("completed_at"):
            doc.completed_at = frappe.utils.now_datetime()
    except Exception:
        pass


@frappe.whitelist()
def get_shift_medications(inpatient_record):
    """Pull today's administered medicines from MAR sheets for the handover chart."""
    out = []
    try:
        today = frappe.utils.nowdate()
        mars = frappe.get_all("Medication Administration Record",
            filters={"inpatient_record": inpatient_record, "mar_date": today},
            pluck="name")
        for m in mars:
            doc = frappe.get_doc("Medication Administration Record", m)
            for e in (doc.get("entries") or []):
                if cint(e.get("given")):
                    out.append({
                        "given_at": str(e.get("administration_time") or ""),
                        "drug_code": e.get("drug_code"),
                        "dose": e.get("dose"),
                        "status": e.get("status") or "Given",
                        "given_by": e.get("administered_by"),
                    })
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_shift_medications")
    return out
