# Copyright (c) 2026, Dagaar
"""Clinical Procedure = the theatre core.

The native healthcare Clinical Procedure drives the operation. This module adds
the theatre workflow on top of it: pre-op gating, OR tracking times, and the
generated operation report. Stock consumption is handled natively by the
Clinical Procedure (consume_stock + its own Complete/Stock Entry).
"""
import frappe
from frappe import _
from frappe.utils import flt, cint, nowdate, now_datetime


def _preop_blockers(inpatient_record):
    """Missing pre-op requirements (empty list == ready for theatre)."""
    missing = []
    if not inpatient_record:
        return missing
    if not frappe.db.count("History Clinical Examination",
                           {"inpatient_record": inpatient_record}):
        missing.append("History & Clinical Examination")
    if not frappe.db.count("Surgical Consent Form",
                           {"inpatient_record": inpatient_record}):
        missing.append("Surgical Consent Form")
    if not frappe.db.count("Pre Operative Checklist",
                           {"inpatient_record": inpatient_record, "ready_for_or": 1}):
        missing.append("Pre-Operative Checklist marked READY FOR OR")
    return missing


@frappe.whitelist()
def ot_facility_query(doctype, txt, searchfield, start, page_len, filters):
    """Service units whose type is flagged as an OT facility."""
    return frappe.db.sql("""
        select su.name
        from `tabHealthcare Service Unit` su
        join `tabHealthcare Service Unit Type` ut on ut.name = su.service_unit_type
        where ifnull(ut.custom_is_ot_facility,0) = 1
          and ifnull(su.is_group,0) = 0
          and su.name like %(txt)s
        order by su.name limit %(start)s, %(page_len)s
    """, {"txt": "%%%s%%" % (txt or ""), "start": start, "page_len": page_len})


def validate_clinical_procedure(doc, method=None):
    """Gate the theatre: block starting surgery until pre-op is complete and no
    invoice is left in DRAFT. Keep the generated report fresh."""
    ir = doc.get("inpatient_record")
    if ir and doc.get("custom_surgery_start"):
        missing = _preop_blockers(ir)
        if missing:
            frappe.throw(_("Pre-op incomplete - finish: {0}.").format(", ".join(missing)))
        try:
            from inpatient_patch.inpatient_patch.billing import assert_no_draft_invoices
            assert_no_draft_invoices(ir, step="the operation")
        except frappe.ValidationError:
            raise
        except Exception:
            pass
    _build_report(doc)


def on_update_clinical_procedure(doc, method=None):
    if doc.get("inpatient_record"):
        try:
            from inpatient_patch.inpatient_patch.workflow import update_stage
            update_stage(doc, method)
        except Exception:
            pass


def _build_report(doc):
    """Compose the human-readable surgery report from the fields."""
    try:
        team = []
        for t in (doc.get("custom_surgical_team") or []):
            who = t.get("member_name") or ""
            role = t.get("role") or ""
            if who:
                team.append("  - {0}{1}".format(who, " ({0})".format(role) if role else ""))
        rows = [
            "OPERATION REPORT",
            "Procedure: {0}".format(doc.get("procedure_template") or ""),
            "Surgeon: {0}".format(doc.get("custom_lead_surgeon") or ""),
            "Anaesthesia: {0}  |  Anaesthetist: {1}".format(
                doc.get("custom_anesthesia_type") or "-", doc.get("custom_anesthetist") or "-"),
            "Time In: {0}".format(doc.get("custom_time_in") or "-"),
            "Surgery: {0} -> {1}".format(doc.get("custom_surgery_start") or "-",
                                         doc.get("custom_surgery_finish") or "-"),
            "Time Out: {0}".format(doc.get("custom_time_out") or "-"),
            "Pre-op Diagnosis: {0}".format(doc.get("custom_preop_diagnosis") or "-"),
            "Post-op Diagnosis: {0}".format(doc.get("custom_postop_diagnosis") or "-"),
            "Procedure Performed: {0}".format(doc.get("custom_procedure_performed") or "-"),
        ]
        if team:
            rows.append("Team:")
            rows.extend(team)
        if doc.get("custom_operation_note"):
            rows.append("Operation Note:\n{0}".format(doc.get("custom_operation_note")))
        if doc.get("custom_findings"):
            rows.append("Findings:\n{0}".format(doc.get("custom_findings")))
        rows.append("Estimated Blood Loss: {0} ml".format(doc.get("custom_blood_loss_ml") or 0))
        rows.append("Drains: {0}".format(doc.get("custom_drains") or "-"))
        rows.append("Sponge/Instrument count correct: {0}".format(
            "Yes" if cint(doc.get("custom_sponge_count_correct")) else "NO"))
        if doc.get("custom_complications"):
            rows.append("Complications: {0}".format(doc.get("custom_complications")))
        doc.custom_surgery_report = "\n".join(rows)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "build surgery report")


def _stamp(cp, field, value=None):
    doc = frappe.get_doc("Clinical Procedure", cp)
    doc.db_set(field, value or now_datetime())
    return doc


@frappe.whitelist()
def cp_time_in(clinical_procedure):
    _stamp(clinical_procedure, "custom_time_in")
    return True


@frappe.whitelist()
def cp_start_surgery(clinical_procedure):
    doc = frappe.get_doc("Clinical Procedure", clinical_procedure)
    missing = _preop_blockers(doc.get("inpatient_record"))
    if missing:
        frappe.throw(_("Cannot start - finish first:<ul>{0}</ul>")
                     .format("".join("<li>{0}</li>".format(m) for m in missing)))
    from inpatient_patch.inpatient_patch.billing import assert_no_draft_invoices
    assert_no_draft_invoices(doc.get("inpatient_record"), step="the operation")
    doc.db_set("custom_surgery_start", now_datetime())
    if not doc.get("custom_time_in"):
        doc.db_set("custom_time_in", now_datetime())
    _notify(doc, "Operation Started", "Your operation has started.")
    return True


@frappe.whitelist()
def cp_finish_surgery(clinical_procedure):
    doc = frappe.get_doc("Clinical Procedure", clinical_procedure)
    if not doc.get("custom_surgery_start"):
        frappe.throw(_("Start the surgery before finishing it."))
    doc.db_set("custom_surgery_finish", now_datetime())
    _notify(doc, "Operation Ended", "Your operation has ended. Moving to recovery.")
    return True


@frappe.whitelist()
def cp_time_out(clinical_procedure):
    _stamp(clinical_procedure, "custom_time_out")
    return True


@frappe.whitelist()
def cp_generate_report(clinical_procedure):
    doc = frappe.get_doc("Clinical Procedure", clinical_procedure)
    _build_report(doc)
    doc.save(ignore_permissions=True)
    return doc.custom_surgery_report


def _notify(doc, title, msg):
    try:
        from inpatient_patch.inpatient_patch.notifications import notify_patient
        if doc.get("inpatient_record"):
            notify_patient(doc.inpatient_record, title, _(msg),
                           ref_dt="Clinical Procedure", ref_dn=doc.name)
    except Exception:
        pass


def validate_preop_checklist(doc, method=None):
    mandatory = ["side_marked", "consent_signed", "npo_confirmed", "iv_line_inserted"]
    doc.ready_for_or = 1 if all(cint(doc.get(m)) for m in mandatory) else 0


def validate_safety_checklist(doc, method=None):
    doc.signin_complete = 1 if all(cint(doc.get(x)) for x in
        ["si_identity_confirmed", "si_procedure_consent", "si_anesthesia_check",
         "si_pulse_oximeter"]) else 0
    doc.timeout_complete = 1 if all(cint(doc.get(x)) for x in
        ["to_team_introduced", "to_surgeon_confirms", "to_anesthesia_confirms",
         "to_nursing_confirms"]) else 0
    doc.signout_complete = 1 if (doc.get("procedure_name") and doc.get("sponge_count")) else 0


def validate_procedure_note(doc, method=None):
    doc.escalated = 1 if (doc.get("sponge_count") == "Incorrect" or
                          (doc.get("complications") or "").strip()) else 0
