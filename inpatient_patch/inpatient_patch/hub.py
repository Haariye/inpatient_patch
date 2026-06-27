# Copyright (c) 2026, Dagaar
"""
Server endpoints powering the Inpatient Record hub UI: create a linked clinical
sheet pre-filled with the record + patient, and fetch the live snapshot.
"""
import frappe
from frappe import _

# map UI key -> (doctype, anchor fieldname on that doctype)
SHEETS = {
    "Emergency Assessment Sheet": ("Emergency Assessment Sheet", "inpatient_record"),
    "Admission Social Data": ("Admission Social Data", "inpatient_record"),
    "Nursing Admission Assessment": ("Nursing Admission Assessment", "inpatient_record"),
    "History Clinical Examination": ("History Clinical Examination", "inpatient_record"),
    "Progress Note": ("Progress Note", "inpatient_record"),
    "Pre Operation Cardiac Review": ("Pre Operation Cardiac Review", "inpatient_record"),
    "Pre Anesthetic Assessment": ("Pre Anesthetic Assessment", "inpatient_record"),
    "Pre Operative Checklist": ("Pre Operative Checklist", "inpatient_record"),
    "Surgical Consent Form": ("Surgical Consent Form", "inpatient_record"),
    "Surgical Safety Checklist": ("Surgical Safety Checklist", "inpatient_record"),
    "OR Tracking Board": ("OR Tracking Board", "inpatient_record"),
    "Operation Procedure Note": ("Operation Procedure Note", "inpatient_record"),
    "Post Operative Checklist": ("Post Operative Checklist", "inpatient_record"),
    "Recovery Nurse Record": ("Recovery Nurse Record", "inpatient_record"),
    "Medication Administration Record": ("Medication Administration Record", "inpatient_record"),
    "Doctor Order": ("Doctor Order", "inpatient_record"),
    "Diabetic Insulin Chart": ("Diabetic Insulin Chart", "inpatient_record"),
    "Daily Round Plan": ("Daily Round Plan", "inpatient_record"),
    "Nurse Handover": ("Nurse Handover", "inpatient_record"),
    "Discharge Summary": ("Discharge Summary", "inpatient_record"),
    "Operation Theatre Case": ("Operation Theatre Case", "inpatient_record"),
    "Inpatient Service Order": ("Inpatient Service Order", "inpatient_record"),
    "Patient Deposit": ("Patient Deposit", "inpatient_record"),
}


@frappe.whitelist()
def new_sheet(inpatient_record, sheet):
    if sheet not in SHEETS:
        frappe.throw(_("Unknown sheet: {0}").format(sheet))
    dt, anchor = SHEETS[sheet]
    patient = frappe.db.get_value("Inpatient Record", inpatient_record, "patient")
    doc = frappe.new_doc(dt)
    doc.set(anchor, inpatient_record)
    if doc.meta.has_field("patient"):
        doc.patient = patient
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def get_snapshot(inpatient_record):
    """Counts of each linked sheet for the hub badges."""
    snap = {}
    for sheet, (dt, anchor) in SHEETS.items():
        try:
            snap[sheet] = frappe.db.count(dt, {anchor: inpatient_record})
        except Exception:
            snap[sheet] = 0
    return snap
