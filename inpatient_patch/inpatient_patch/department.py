# Copyright (c) 2026, Dagaar
"""
Department admission protocols.

When an Inpatient Record is created, find the protocol for its medical
department and:
  * stamp the protocol + surgical flag onto the record,
  * leave a guidance comment listing the required forms for that department,
  * (optionally) the front-end uses get_protocol() to render the correct
    department-specific checklist of forms.
"""
import frappe
from frappe import _


def apply_admission_protocol(doc, method=None):
    """Stamp the department protocol onto a new Inpatient Record and post a
    guidance comment. Wrapped so it can NEVER block the native admission flow
    (e.g. the 'Schedule Admission' button on Patient Encounter)."""
    try:
        _apply_admission_protocol(doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "apply_admission_protocol")


def _apply_admission_protocol(doc):
    dept = doc.get("custom_medical_department") or doc.get("medical_department")
    if dept and not doc.get("custom_medical_department"):
        # mirror the native medical_department into our field for convenience
        doc.db_set("custom_medical_department", dept, update_modified=False)
    if not dept:
        prac = doc.get("primary_practitioner")
        if prac:
            dept = frappe.db.get_value("Healthcare Practitioner", prac, "department")
            if dept:
                doc.db_set("custom_medical_department", dept, update_modified=False)
    if not dept:
        return

    protocol = frappe.db.get_value("Department Admission Protocol",
                                   {"medical_department": dept, "enabled": 1}, "name")
    if not protocol:
        return

    doc.db_set("custom_admission_protocol", protocol, update_modified=False)

    pdoc = frappe.get_doc("Department Admission Protocol", protocol)
    forms = sorted(pdoc.required_forms, key=lambda r: (r.sequence or 0))
    if forms:
        lines = "".join(
            f"<li>[{r.stage}] {r.form}{' <b>(required)</b>' if r.mandatory else ''}</li>"
            for r in forms)
        doc.add_comment("Comment",
            _("<b>{0} admission protocol applied.</b> Required workflow:<ul>{1}</ul>")
            .format(dept, lines))

    # notify the patient that admission has started
    try:
        from inpatient_patch.inpatient_patch.notifications import notify_patient
        notify_patient(doc.name, "Admission",
                       _("You have been admitted under {0}. Your care plan has started.")
                       .format(dept), ref_dt="Inpatient Record", ref_dn=doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "admission notify")


@frappe.whitelist()
def get_protocol(inpatient_record):
    """Return the ordered required forms + default order set for the record's
    department (used by the Inpatient Record hub UI)."""
    dept = frappe.db.get_value("Inpatient Record", inpatient_record,
                               "custom_medical_department")
    if not dept:
        return {"department": None, "forms": [], "order_set": []}
    protocol = frappe.db.get_value("Department Admission Protocol",
                                   {"medical_department": dept, "enabled": 1}, "name")
    if not protocol:
        return {"department": dept, "forms": [], "order_set": []}
    pdoc = frappe.get_doc("Department Admission Protocol", protocol)
    return {
        "department": dept,
        "is_surgical": pdoc.is_surgical,
        "forms": [
            {"stage": r.stage, "form": r.form, "mandatory": r.mandatory,
             "sequence": r.sequence}
            for r in sorted(pdoc.required_forms, key=lambda r: (r.sequence or 0))
        ],
        "order_set": [
            {"item_type": r.item_type, "item_code": r.item_code,
             "item_name": r.item_name, "default_qty": r.default_qty, "notes": r.notes}
            for r in pdoc.order_set
        ],
    }
