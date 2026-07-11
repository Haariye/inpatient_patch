# Copyright (c) 2026, Dagaar
"""Nurse Handover - one dashboard per admission.

Opens when the patient is admitted (created from the Inpatient Record button),
auto-closes at discharge. The form renders as a dashboard (charts + pending
tasks + medicines) built from the doctypes the nurse already fills; each shift's
nurse writes a handover row and the next nurse acknowledges it.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist()
def get_or_create_handover(inpatient_record):
    """Return the open Nurse Handover for this admission, creating it if needed."""
    existing = frappe.db.get_value("Nurse Handover",
        {"inpatient_record": inpatient_record}, "name")
    if existing:
        _sync_status(existing)
        return existing
    ip = frappe.get_doc("Inpatient Record", inpatient_record)
    doc = frappe.new_doc("Nurse Handover")
    doc.inpatient_record = ip.name
    doc.patient = ip.patient
    doc.patient_name = ip.patient_name
    if ip.meta.has_field("admission_scheduled_datetime") and ip.get("admission_scheduled_datetime"):
        doc.admission_date = str(ip.admission_scheduled_datetime)[:10]
    elif ip.meta.has_field("scheduled_date"):
        doc.admission_date = ip.get("scheduled_date")
    doc.responsible_nurse = ip.get("custom_responsible_nurse")
    doc.status = "Closed" if ip.status == "Discharged" else "Open"
    doc.last_updated = now_datetime()
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    return doc.name


def _sync_status(name):
    ir = frappe.db.get_value("Nurse Handover", name, "inpatient_record")
    if ir:
        st = frappe.db.get_value("Inpatient Record", ir, "status")
        want = "Closed" if st == "Discharged" else "Open"
        if frappe.db.get_value("Nurse Handover", name, "status") != want:
            frappe.db.set_value("Nurse Handover", name, "status", want,
                                update_modified=False)


def close_on_discharge(doc, method=None):
    """Hook: when a Discharge Summary is submitted, close the patient's handover."""
    ir = doc.get("inpatient_record")
    if not ir:
        return
    nh = frappe.db.get_value("Nurse Handover", {"inpatient_record": ir}, "name")
    if nh:
        frappe.db.set_value("Nurse Handover", nh, "status", "Closed",
                            update_modified=False)


def stamp_updated(doc, method=None):
    doc.last_updated = now_datetime()
    for row in (doc.get("shift_handovers") or []):
        if row.acknowledged and not row.acknowledged_at:
            row.acknowledged_at = now_datetime()
