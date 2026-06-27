# Copyright (c) 2026, Dagaar
"""
Operation Theatre logic.

On submit of an Operation Theatre Case:
  1. Issue all consumables / implants (screws) from stock via a Material Issue
     Stock Entry.
  2. Create a DRAFT-but-billable consumable/pharmacy Sales Invoice for those
     items against the patient (same draft-billable pattern as pharmacy).
Also enforces the safety gates from the specification.
"""
import frappe
from frappe import _
from frappe.utils import flt, cint, nowdate

from inpatient_patch.inpatient_patch.billing import get_customer, get_settings, \
    refresh_inpatient_billing_summary, _company


# ---- validation gates -----------------------------------------------------
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
    doc.signout_complete = 1 if (doc.procedure_name and doc.sponge_count) else 0


def validate_procedure_note(doc, method=None):
    doc.escalated = 1 if (doc.sponge_count == "Incorrect" or
                          (doc.complications or "").strip()) else 0


# ---- main submit ----------------------------------------------------------
def on_submit_ot_case(doc, method=None):
    if doc.consumables and not cint(doc.consumables_issued):
        _issue_consumables_to_stock(doc)
        _create_consumable_invoice(doc)
    # mark the inpatient record as operated
    if doc.inpatient_record:
        frappe.db.set_value("Inpatient Record", doc.inpatient_record,
                            "custom_operated", 1, update_modified=False)
    if doc.get("status") != "Completed":
        doc.db_set("status", "Completed")
    try:
        from inpatient_patch.inpatient_patch.notifications import notify_patient
        notify_patient(doc.inpatient_record, "Operation",
                       _("Your operation ({0}) has been completed and recorded.")
                       .format(doc.planned_procedure or ""),
                       ref_dt="Operation Theatre Case", ref_dn=doc.name)
    except Exception:
        pass


def on_cancel_ot_case(doc, method=None):
    if doc.get("stock_entry") and frappe.db.exists("Stock Entry", doc.stock_entry):
        se = frappe.get_doc("Stock Entry", doc.stock_entry)
        if se.docstatus == 1:
            se.cancel()
    if doc.get("consumable_invoice") and frappe.db.exists("Sales Invoice", doc.consumable_invoice):
        si = frappe.get_doc("Sales Invoice", doc.consumable_invoice)
        if si.docstatus == 0:
            si.add_comment("Comment", _("OT Case {0} cancelled - review draft invoice.")
                           .format(doc.name))


def _issue_consumables_to_stock(doc):
    warehouse = doc.get("warehouse") or frappe.db.get_single_value(
        "Stock Settings", "default_warehouse")
    if not warehouse:
        frappe.throw(_("Set an 'Issue From Warehouse' on the OT Case (or a default warehouse)."))

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Issue"
    se.purpose = "Material Issue"
    se.company = _company(doc.as_dict())
    se.remarks = _("OT consumables for {0} ({1})").format(doc.patient, doc.name)

    any_stock = False
    for r in doc.consumables:
        if not frappe.db.get_value("Item", r.item_code, "is_stock_item"):
            continue
        any_stock = True
        item = se.append("items", {})
        item.item_code = r.item_code
        item.qty = flt(r.qty) or 1
        item.s_warehouse = warehouse
        if r.get("serial_no"):
            item.serial_no = r.serial_no
        if r.get("batch_no"):
            item.batch_no = r.batch_no

    if not any_stock:
        return
    se.set_missing_values()
    se.insert(ignore_permissions=True)
    se.submit()
    doc.db_set("stock_entry", se.name)
    doc.db_set("consumables_issued", 1)


def _create_consumable_invoice(doc):
    customer = get_customer(doc.patient)
    if not customer:
        frappe.throw(_("Patient {0} has no linked Customer.").format(doc.patient))
    settings = get_settings()

    inv = frappe.new_doc("Sales Invoice")
    inv.customer = customer
    inv.patient = doc.patient
    inv.company = _company(doc.as_dict())
    inv.currency = settings.currency or "USD"
    inv.posting_date = nowdate()
    inv.due_date = nowdate()
    inv.custom_inpatient_record = doc.inpatient_record
    inv.custom_is_consumable_invoice = 1
    inv.custom_ot_case = doc.name
    inv.remarks = _("OT consumables & implants for {0}").format(doc.name)

    has_rows = False
    for r in doc.consumables:
        if cint(r.billed):
            continue
        has_rows = True
        child = inv.append("items", {})
        child.item_code = r.item_code
        child.qty = flt(r.qty) or 1
        if flt(r.rate):
            child.rate = flt(r.rate)
        label = r.item_name or r.item_code
        if cint(r.is_implant):
            label += _(" [IMPLANT {0}]").format(r.serial_no or "")
        child.description = label
        child.custom_ot_consumable_row_id = r.name
        child.custom_inpatient_record = doc.inpatient_record

    if not has_rows:
        return
    inv.set_missing_values()
    inv.calculate_taxes_and_totals()
    inv.insert(ignore_permissions=True)   # DRAFT but billable
    doc.db_set("consumable_invoice", inv.name)
    refresh_inpatient_billing_summary(doc.inpatient_record)
