# Copyright (c) 2026, Dagaar
"""
Somali billing engine for the inpatient suite.

Design (per requirements):
  * The DAILY scheduler bills ONLY the bed (one draft invoice per patient/day).
  * Every other service (pharmacy, lab, radiology, OT consumables) becomes a
    DRAFT-but-billable Sales Invoice the moment a nurse/doctor "sends" it -
    mirroring the consultation -> drug-prescription -> invoice flow.
  * A one-click Deposit creates a submitted Payment Entry (advance) for the
    patient's customer and is reflected in the Inpatient Record summary.
Currency: USD.
"""
import frappe
from frappe import _
from frappe.utils import flt, cint, nowdate, now_datetime, getdate, get_datetime


# ===========================================================================
# helpers
# ===========================================================================
def get_settings():
    return frappe.get_single("Inpatient Billing Settings")


def get_customer(patient):
    cust = frappe.db.get_value("Patient", patient, "customer")
    if cust:
        return cust
    link = frappe.get_all("Dynamic Link", filters={
        "link_doctype": "Patient", "link_name": patient, "parenttype": "Customer",
    }, fields=["parent"], limit=1)
    return link[0].parent if link else None


def _company(ip):
    return ip.get("company") or frappe.defaults.get_user_default("Company") \
        or frappe.db.get_single_value("Global Defaults", "default_company")


# ===========================================================================
# 1. DAILY BED BILLING  (scheduler - hourly, acts only at configured hour)
# ===========================================================================
def run_daily_bed_billing():
    settings = get_settings()
    if not cint(settings.auto_bed_billing_enabled):
        return

    run_hour = cint(settings.daily_run_hour or 12)
    if now_datetime().hour != run_hour:
        return  # only fire once per day, at the configured hour

    today = nowdate()
    active = frappe.get_all(
        "Inpatient Record",
        filters={"status": "Admitted"},
        fields=["name", "patient", "company", "custom_current_bed",
                "custom_last_bed_billed_date"],
    )
    for ip in active:
        if ip.custom_last_bed_billed_date and getdate(ip.custom_last_bed_billed_date) >= getdate(today):
            continue
        try:
            bill_bed_for_record(ip.name, posting_date=today)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), f"Bed billing failed: {ip.name}")


def _bed_rate_and_item(ip_doc):
    """Resolve the daily bed rate + item from the current bed's service-unit type."""
    bed = ip_doc.get("custom_current_bed")
    if not bed:
        # fall back to the latest occupancy row on the inpatient record
        occ = ip_doc.get("inpatient_occupancies") or []
        if occ:
            bed = occ[-1].service_unit
    if not bed:
        return None, 0, None

    unit_type = frappe.db.get_value("Healthcare Service Unit", bed, "service_unit_type")
    rate, item = 0, None
    if unit_type:
        item, rate = frappe.db.get_value(
            "Healthcare Service Unit Type", unit_type,
            ["custom_bed_item", "custom_daily_bed_rate"]) or (None, 0)
    return bed, flt(rate), item


@frappe.whitelist()
def bill_bed_for_record(inpatient_record, posting_date=None):
    posting_date = posting_date or nowdate()
    ip = frappe.get_doc("Inpatient Record", inpatient_record)
    settings = get_settings()

    bed, rate, item = _bed_rate_and_item(ip)
    if not bed:
        frappe.throw(_("No current bed set on {0}; cannot bill bed.").format(inpatient_record))
    if rate <= 0 or not item:
        frappe.throw(_("Set 'Daily Bed Rate' and 'Bed Charge Item' on the "
                       "Service Unit Type of bed {0}.").format(bed))

    customer = get_customer(ip.patient)
    if not customer:
        frappe.throw(_("Patient {0} has no linked Customer.").format(ip.patient))

    inv = frappe.new_doc("Sales Invoice")
    inv.customer = customer
    inv.patient = ip.patient
    inv.company = _company(ip.as_dict())
    inv.currency = settings.currency or "USD"
    inv.posting_date = posting_date
    inv.due_date = posting_date
    inv.custom_inpatient_record = ip.name
    inv.custom_is_inpatient_bed_invoice = 1
    inv.custom_bed_billed_date = posting_date
    inv.remarks = _("Daily bed charge for {0} ({1})").format(ip.name, posting_date)

    row = inv.append("items", {})
    row.item_code = item
    row.qty = 1
    row.rate = rate
    row.description = _("Bed / accommodation - {0} - {1}").format(bed, posting_date)
    row.custom_inpatient_record = ip.name

    inv.set_missing_values()
    inv.calculate_taxes_and_totals()
    inv.insert(ignore_permissions=True)   # stays DRAFT (unpaid, billable)

    frappe.db.set_value("Inpatient Record", ip.name,
                        "custom_last_bed_billed_date", posting_date,
                        update_modified=False)
    refresh_inpatient_billing_summary(ip)
    try:
        from inpatient_patch.inpatient_patch.notifications import notify_patient
        notify_patient(ip.name, "Bed Charge",
                       _("A daily bed charge of {0} {1} was posted to your account.")
                       .format(settings.currency or "USD", rate),
                       ref_dt="Sales Invoice", ref_dn=inv.name)
    except Exception:
        pass
    return inv.name


# ===========================================================================
# 2. SERVICE ORDER -> DRAFT BILLABLE INVOICE  (pharmacy/lab/radiology/...)
# ===========================================================================
@frappe.whitelist()
def _resolve_template_item(doctype, name):
    """Return the billing Item linked to a Lab Test / Clinical Procedure Template."""
    if not name:
        return None
    for field in ("item", "item_code"):
        if frappe.get_meta(doctype).has_field(field):
            val = frappe.db.get_value(doctype, name, field)
            if val:
                return val
    return None


def _collect_order_rows(so):
    """Flatten the encounter-style tables into billable rows:
       {row_dt, row_name, item_code, qty, rate, desc}."""
    rows = []
    for r in (so.get("lab_tests") or []):
        if cint(r.get("billed")):
            continue
        item = _resolve_template_item("Lab Test Template", r.lab_test_template)
        if not item:
            frappe.throw(_("Lab Test Template <b>{0}</b> has no billing Item set. "
                           "Set its Item, or remove the row.").format(r.lab_test_template))
        rows.append({"row_dt": "Inpatient Lab Order", "row_name": r.name,
                     "item_code": item, "qty": flt(r.qty) or 1, "rate": flt(r.rate),
                     "desc": r.lab_test_name or r.lab_test_template})
    for r in (so.get("procedures") or []):
        if cint(r.get("billed")):
            continue
        item = _resolve_template_item("Clinical Procedure Template", r.procedure_template)
        if not item:
            frappe.throw(_("Clinical Procedure Template <b>{0}</b> has no billing Item set. "
                           "Set its Item, or remove the row.").format(r.procedure_template))
        rows.append({"row_dt": "Inpatient Procedure Order", "row_name": r.name,
                     "item_code": item, "qty": flt(r.qty) or 1, "rate": flt(r.rate),
                     "desc": r.procedure_name or r.procedure_template})
    for r in (so.get("items") or []):
        if cint(r.get("billed")):
            continue
        rows.append({"row_dt": "Inpatient Item Order", "row_name": r.name,
                     "item_code": r.item_code, "qty": flt(r.qty) or 1,
                     "rate": flt(r.rate), "desc": r.item_name or r.item_code})
    return rows


def send_service_order_to_billing(service_order):
    so = frappe.get_doc("Inpatient Service Order", service_order)

    rows = _collect_order_rows(so)
    if not rows:
        frappe.throw(_("Nothing to bill: add lab tests, procedures or items first "
                       "(or all rows are already billed)."))

    ip = frappe.get_doc("Inpatient Record", so.inpatient_record)
    customer = get_customer(so.patient)
    if not customer:
        frappe.throw(_("Patient {0} has no linked Customer.").format(so.patient))
    settings = get_settings()

    inv = frappe.new_doc("Sales Invoice")
    inv.customer = customer
    inv.patient = so.patient
    inv.company = _company(ip.as_dict())
    inv.currency = settings.currency or "USD"
    inv.posting_date = nowdate()
    inv.due_date = nowdate()
    inv.custom_inpatient_record = so.inpatient_record
    inv.custom_is_inpatient_service_invoice = 1
    inv.custom_inpatient_service_order = so.name
    inv.remarks = _("Inpatient services from {0}").format(so.name)

    for r in rows:
        child = inv.append("items", {})
        child.item_code = r["item_code"]
        child.qty = r["qty"]
        if r["rate"]:
            child.rate = r["rate"]
        child.description = r["desc"]
        child.custom_service_charge_row_id = "{0}:{1}".format(r["row_dt"], r["row_name"])
        child.custom_inpatient_record = so.inpatient_record

    inv.set_missing_values()
    inv.calculate_taxes_and_totals()
    inv.insert(ignore_permissions=True)   # DRAFT but billable

    so.db_set("sales_invoice", inv.name)
    so.db_set("status", "Sent (Billable)")
    refresh_inpatient_billing_summary(ip)
    try:
        from inpatient_patch.inpatient_patch.notifications import notify_patient
        notify_patient(so.inpatient_record, "New Bill",
                       _("A new bill has been generated for you."),
                       ref_dt="Sales Invoice", ref_dn=inv.name)
    except Exception:
        pass
    return inv.name


@frappe.whitelist()
def fetch_lab_findings(patient, inpatient_record=None):
    """Return this patient's lab tests (most recent first) as finding rows for the
    Emergency Assessment / examination lab-findings table."""
    out = []
    try:
        names = frappe.get_all("Lab Test",
            filters={"patient": patient}, order_by="modified desc",
            pluck="name", limit=50)
    except Exception:
        names = []
    for nm in names:
        try:
            lt = frappe.get_doc("Lab Test", nm)
        except Exception:
            continue
        finding = ""
        try:
            parts = []
            for it in (lt.get("normal_test_items") or []):
                val = it.get("result_value")
                lab = it.get("lab_test_name") or it.get("lab_test_particulars")
                if val:
                    parts.append("{0}: {1}".format(lab, val))
            finding = "; ".join(parts)
        except Exception:
            finding = ""
        out.append({
            "lab_test": lt.name,
            "test_name": lt.get("lab_test_name") or lt.name,
            "status": lt.get("status") or "",
            "result_date": str(lt.get("result_date") or "")[:10],
            "finding": finding,
        })
    return out


def on_submit_sales_invoice(doc, method=None):
    """When any inpatient invoice is submitted, mark its source rows billed and
    refresh the record summary."""
    # service order rows (row id stored as "RowDocType:RowName")
    if cint(getattr(doc, "custom_is_inpatient_service_invoice", 0)):
        for item in doc.items:
            row_id = item.get("custom_service_charge_row_id") or ""
            if ":" in row_id:
                row_dt, _sep, row_name = row_id.partition(":")
                if row_name and frappe.db.exists(row_dt, row_name):
                    frappe.db.set_value(row_dt, row_name,
                                        {"billed": 1, "billed_invoice": doc.name},
                                        update_modified=False)
        if doc.get("custom_inpatient_service_order"):
            _refresh_service_order_status(doc.custom_inpatient_service_order)

    # OT consumable rows
    if cint(getattr(doc, "custom_is_consumable_invoice", 0)):
        for item in doc.items:
            row_id = item.get("custom_ot_consumable_row_id")
            if row_id and frappe.db.exists("OT Consumable Line", row_id):
                frappe.db.set_value("OT Consumable Line", row_id,
                                    {"billed": 1, "billed_invoice": doc.name},
                                    update_modified=False)

    if doc.get("custom_inpatient_record"):
        refresh_inpatient_billing_summary(doc.custom_inpatient_record)


def on_cancel_sales_invoice(doc, method=None):
    if doc.get("custom_inpatient_record"):
        refresh_inpatient_billing_summary(doc.custom_inpatient_record)


def on_cancel_service_order(doc, method=None):
    inv = doc.get("sales_invoice")
    if inv and frappe.db.exists("Sales Invoice", inv):
        si = frappe.db.get_value("Sales Invoice", inv, "docstatus")
        if si == 0:
            frappe.get_doc("Sales Invoice", inv).add_comment(
                "Comment", _("Source Service Order {0} cancelled - review this draft.")
                .format(doc.name))


def _refresh_service_order_status(name):
    so = frappe.get_doc("Inpatient Service Order", name)
    allrows = (list(so.get("lab_tests") or []) + list(so.get("procedures") or [])
               + list(so.get("items") or []))
    total = len(allrows)
    billed = len([r for r in allrows if cint(r.get("billed"))])
    if not total:
        return
    status = "Billed" if billed == total else ("Partially Billed" if billed else "Sent (Billable)")
    so.db_set("status", status)


# ===========================================================================
# 3. DEPOSIT  -> Payment Entry (advance)
# ===========================================================================
def on_submit_deposit(doc, method=None):
    if doc.get("payment_entry"):
        return
    customer = doc.get("customer") or get_customer(doc.patient)
    if not customer:
        frappe.throw(_("No customer linked to patient {0}").format(doc.patient))

    settings = get_settings()
    company = settings.default_company or frappe.defaults.get_user_default("Company")

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = customer
    pe.company = company
    pe.posting_date = getdate(doc.deposit_date) if doc.deposit_date else nowdate()
    pe.paid_amount = flt(doc.amount)
    pe.received_amount = flt(doc.amount)
    pe.mode_of_payment = doc.mode_of_payment or settings.deposit_mode_of_payment
    pe.reference_no = doc.name
    pe.reference_date = pe.posting_date
    pe.remarks = doc.remarks or _("Inpatient deposit {0}").format(doc.name)
    # treat as advance
    if hasattr(pe, "is_advance"):
        pe.is_advance = "Yes"
    try:
        pe.setup_party_account_field()
        pe.set_missing_values()
    except Exception:
        pass
    pe.insert(ignore_permissions=True)
    pe.submit()

    doc.db_set("payment_entry", pe.name)
    refresh_inpatient_billing_summary(doc.inpatient_record)
    try:
        from inpatient_patch.inpatient_patch.notifications import notify_patient
        notify_patient(doc.inpatient_record, "Deposit Received",
                       _("Your deposit of {0} has been received. Thank you.")
                       .format(flt(doc.amount)),
                       ref_dt="Patient Deposit", ref_dn=doc.name)
    except Exception:
        pass


def on_cancel_deposit(doc, method=None):
    pe = doc.get("payment_entry")
    if pe and frappe.db.exists("Payment Entry", pe):
        pdoc = frappe.get_doc("Payment Entry", pe)
        if pdoc.docstatus == 1:
            pdoc.cancel()
    refresh_inpatient_billing_summary(doc.inpatient_record)


# ===========================================================================
# 4. SUMMARY ROLLUP on Inpatient Record
# ===========================================================================
def refresh_inpatient_billing_summary(record, method=None):
    """Roll up billed/paid/deposit/outstanding onto the Inpatient Record.

    Registered as an `on_update` doc-event (called as (doc, method)) AND called
    internally with a name string. Must never raise - it augments a native
    healthcare save and must not block it.
    """
    try:
        name = record if isinstance(record, str) else record.name
        if not name or not frappe.db.exists("Inpatient Record", name):
            return

        billed = frappe.db.sql("""
            select coalesce(sum(grand_total),0), coalesce(sum(outstanding_amount),0),
                   coalesce(sum(grand_total-outstanding_amount),0)
            from `tabSales Invoice`
            where custom_inpatient_record=%s and docstatus=1
        """, name)[0]
        total_billed, outstanding, paid = flt(billed[0]), flt(billed[1]), flt(billed[2])

        deposit = frappe.db.sql("""
            select coalesce(sum(amount),0) from `tabPatient Deposit`
            where inpatient_record=%s and docstatus=1
        """, name)[0][0]
        deposit = flt(deposit)

        frappe.db.set_value("Inpatient Record", name, {
            "custom_total_billed": total_billed,
            "custom_total_paid": paid,
            "custom_total_deposit": deposit,
            "custom_outstanding": max(outstanding - deposit, 0),
        }, update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Inpatient billing summary refresh")
