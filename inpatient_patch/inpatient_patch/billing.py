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
    """Resolve the daily bed rate + item from the current bed's service-unit type
    using the NATIVE item_code + rate fields on Healthcare Service Unit Type."""
    bed = ip_doc.get("custom_current_bed")
    if not bed:
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
            ["item_code", "rate"]) or (None, 0)
    return bed, flt(rate), item


def _admission_date(ip):
    val = ip.get("admitted_datetime") or ip.get("scheduled_date")
    if not val:
        return None
    return getdate(val)


def _bed_days_allowed_and_billed(ip):
    """Allowed bed-days = days from admission up to today (or discharge) inclusive.
    Billed = number of submitted bed invoices already raised for this record."""
    adm = _admission_date(ip)
    if not adm:
        return 0, 0
    end = getdate(ip.get("discharge_datetime")) if ip.get("discharge_datetime") else getdate(nowdate())
    allowed = (end - adm).days + 1
    if allowed < 1:
        allowed = 1
    billed = frappe.db.count("Sales Invoice",
        {"custom_inpatient_record": ip.name, "custom_is_inpatient_bed_invoice": 1,
         "docstatus": ["<", 2]})
    return allowed, billed


@frappe.whitelist()
def bill_bed_for_record(inpatient_record, posting_date=None):
    posting_date = posting_date or nowdate()
    ip = frappe.get_doc("Inpatient Record", inpatient_record)
    settings = get_settings()

    bed, rate, item = _bed_rate_and_item(ip)
    if not bed:
        frappe.throw(_("No current bed set on {0}; cannot bill bed.").format(inpatient_record))
    if rate <= 0 or not item:
        frappe.throw(_("Set the <b>Item Code</b> and <b>Rate</b> on the Service Unit "
                       "Type of bed {0}.").format(bed))

    # ---- over-billing guard: never bill more bed-days than the stay ----
    allowed, billed = _bed_days_allowed_and_billed(ip)
    if billed >= allowed:
        frappe.throw(_("Bed already billed for all {0} day(s) of this stay. "
                       "You cannot bill more bed-days than the patient has stayed.")
                     .format(allowed))
    # don't double-bill the same day
    if frappe.db.exists("Sales Invoice",
            {"custom_inpatient_record": ip.name, "custom_is_inpatient_bed_invoice": 1,
             "custom_bed_billed_date": posting_date, "docstatus": ["<", 2]}):
        frappe.throw(_("The bed is already billed for {0}.").format(posting_date))

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
    inv.insert(ignore_permissions=True)
    try:
        inv.submit()   # bed invoices are SUBMITTED immediately
    except Exception:
        frappe.log_error(frappe.get_traceback(), "bed invoice submit")

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
    for r in (so.get("imaging") or []):
        if cint(r.get("billed")):
            continue
        item = _resolve_template_item("Lab Test Template", r.lab_test_template)
        if not item:
            frappe.throw(_("Imaging template <b>{0}</b> has no billing Item set. "
                           "Set its Item, or remove the row.").format(r.lab_test_template))
        rows.append({"row_dt": "Inpatient Imaging Order", "row_name": r.name,
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


_PATIENT_GROUPS = ("Patient", "Patients")


def _account_totals(ip_name):
    """Return (invoiced, paid, drafts) for an inpatient record's submitted SIs."""
    row = frappe.db.sql("""
        select coalesce(sum(grand_total),0), coalesce(sum(grand_total-outstanding_amount),0)
        from `tabSales Invoice`
        where custom_inpatient_record=%s and docstatus=1
    """, ip_name)[0]
    invoiced, paid = flt(row[0]), flt(row[1])
    drafts = frappe.db.count("Sales Invoice",
        {"custom_inpatient_record": ip_name, "docstatus": 0})
    return invoiced, paid, drafts


def discharge_block_reason(ip):
    """Block discharge unless invoices == payments (fully settled), OR the patient
    is Sponsored (Sponsors ticked AND customer group not Patient/Patients).
    Patient/Patients groups pay cash and must be fully paid."""
    if isinstance(ip, str):
        ip = frappe.get_doc("Inpatient Record", ip)
    # surgery must be fully completed before discharge
    if (ip.get("custom_care_type") == "Surgery"):
        need = []
        if not frappe.db.count("Operation Procedure Note", {"inpatient_record": ip.name}) \
                and not frappe.db.sql("select 1 from `tabClinical Procedure` where "
                "inpatient_record=%s and (custom_surgery_finish is not null or status='Completed') "
                "limit 1", ip.name):
            need.append("the operation (Clinical Procedure finished / Procedure Note)")
        if not frappe.db.count("Recovery Nurse Record", {"inpatient_record": ip.name}):
            need.append("Recovery Nurse Record")
        if not frappe.db.count("Post Operative Checklist", {"inpatient_record": ip.name}):
            need.append("Post-Operative Checklist")
        if need:
            return ("Cannot discharge a Surgery case \u2014 finish the operation steps "
                    "first: {0}.").format(", ".join(need))
    customer = get_customer(ip.patient)
    group = frappe.db.get_value("Customer", customer, "customer_group") if customer else None
    invoiced, paid, drafts = _account_totals(ip.name)
    if drafts:
        return ("Cannot discharge: {0} invoice(s) are still DRAFT. Ask Reception / "
                "Pharmacy to submit them first.").format(drafts)
    # Sponsored waive: only for non-Patient customer groups
    if cint(ip.get("custom_is_sponsored")):
        if group and group not in _PATIENT_GROUPS:
            return None
        return ("'Sponsors' waive is not allowed for a cash patient (Customer Group "
                "'{0}'). Update the Customer Group to the sponsor first.").format(group or "Patient")
    outstanding = flt(invoiced) - flt(paid)
    if outstanding > 0:
        return ("Cannot discharge: invoices ({0}) and payments ({1}) do not match \u2014 "
                "outstanding {2}. Collect the balance, or tick 'Sponsors' for a "
                "sponsored (non-cash) patient.").format(invoiced, paid, outstanding)
    return None


@frappe.whitelist()
def discharge_overpaid_amount(inpatient_record):
    """How much the patient has paid ABOVE what was invoiced (refundable)."""
    invoiced, paid, _drafts = _account_totals(inpatient_record)
    deposit = flt(frappe.db.sql("""select coalesce(sum(amount),0) from `tabPatient Deposit`
        where inpatient_record=%s and docstatus=1""", inpatient_record)[0][0])
    # paid already includes reconciled deposits; unapplied deposit is extra credit
    extra = max(flt(paid) - flt(invoiced), 0) + max(flt(deposit) - flt(paid), 0)
    return flt(extra)


@frappe.whitelist()
def create_refund_journal_entry(inpatient_record, amount=None):
    """Create a DRAFT Journal Entry returning the patient's extra payment."""
    amount = flt(amount) if amount else discharge_overpaid_amount(inpatient_record)
    if amount <= 0:
        frappe.msgprint(_("Nothing to refund."))
        return None
    ip = frappe.get_doc("Inpatient Record", inpatient_record)
    customer = get_customer(ip.patient)
    settings = get_settings()
    company = settings.default_company or frappe.defaults.get_user_default("Company")
    try:
        from erpnext.accounts.party import get_party_account
        receivable = get_party_account("Customer", customer, company)
    except Exception:
        receivable = frappe.get_cached_value("Company", company, "default_receivable_account")
    cash = (settings.get("deposit_account")
            or frappe.get_cached_value("Company", company, "default_cash_account")
            or frappe.get_cached_value("Company", company, "default_bank_account"))
    if not receivable or not cash:
        frappe.throw(_("Set a cash/receivable account to create the refund entry."))
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = company
    je.posting_date = nowdate()
    je.user_remark = _("Refund of extra payment for {0}").format(inpatient_record)
    je.append("accounts", {"account": receivable, "party_type": "Customer",
                           "party": customer, "debit_in_account_currency": amount})
    je.append("accounts", {"account": cash, "credit_in_account_currency": amount})
    je.flags.ignore_mandatory = True
    je.insert(ignore_permissions=True)
    frappe.msgprint(_("Draft refund Journal Entry {0} created for {1}.").format(je.name, amount))
    return je.name


def guard_inpatient_discharge(doc, method=None):
    """Block the NATIVE schedule-discharge / discharge when the bill is unpaid."""
    try:
        if doc.get("status") in ("Discharge Scheduled", "Discharged"):
            reason = discharge_block_reason(doc)
            if reason:
                frappe.throw(_(reason))
    except frappe.ValidationError:
        raise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "guard_inpatient_discharge")


def has_bed_invoice(inpatient_record):
    """True once Bill Bed Now has created a bed invoice for this admission."""
    return bool(frappe.db.exists("Sales Invoice", {
        "custom_inpatient_record": inpatient_record,
        "custom_is_inpatient_bed_invoice": 1}))


def assert_bed_invoice(inpatient_record):
    """Block clinical actions after admit until the first bed invoice exists."""
    status = frappe.db.get_value("Inpatient Record", inpatient_record, "status")
    if status == "Admitted" and not has_bed_invoice(inpatient_record):
        frappe.throw(_("Please click <b>Bill Bed Now</b> first \u2014 no action is allowed "
                       "until the bed invoice has been created for this admission."))


@frappe.whitelist()
def get_finance_access():
    """True if the current user may see financial buttons/cards."""
    defaults = {"System Manager", "Healthcare Administrator", "Accounts User",
                "Accounts Manager"}
    try:
        s = get_settings()
        configured = {r.role for r in (s.get("finance_roles") or []) if r.get("role")}
    except Exception:
        configured = set()
    allowed = configured or defaults
    user_roles = set(frappe.get_roles())
    return bool(user_roles & allowed)


@frappe.whitelist()
def admit_from_emergency(emergency):
    """Create an Inpatient Record populated from the Emergency Assessment Sheet so
    the user does NOT re-type patient details. Returns the new record name."""
    ea = frappe.get_doc("Emergency Assessment Sheet", emergency)
    if ea.get("inpatient_record"):
        return ea.inpatient_record

    ip = frappe.new_doc("Inpatient Record")
    ip.patient = ea.patient
    ip.patient_name = ea.get("patient_name")
    # pull identity from the Patient master
    for src, dst in (("sex", "gender"), ("dob", "dob"), ("blood_group", "blood_group")):
        val = frappe.db.get_value("Patient", ea.patient, src)
        if val and ip.meta.has_field(dst):
            ip.set(dst, val)
    if ea.get("gp_in_charge") and ip.meta.has_field("primary_practitioner"):
        ip.primary_practitioner = ea.gp_in_charge
    # our custom fields
    ip.custom_mode_of_admission = "Emergency"
    ip.custom_emergency_done = 1
    ip.custom_care_type = "Treatment"
    if ea.get("gp_in_charge"):
        ip.custom_admitting_doctor = ea.gp_in_charge
        dept = frappe.db.get_value("Healthcare Practitioner", ea.gp_in_charge, "department")
        if dept:
            if ip.meta.has_field("medical_department"):
                ip.medical_department = dept
    # copy the encounter-style child tables 1:1 into the Inpatient Record
    _copy_child(ea, ip, "chief_complaint")
    _copy_child(ea, ip, "diagnosis")
    _copy_child(ea, ip, "drug_prescription")
    _copy_child(ea, ip, "lab_test_prescription")
    _copy_child(ea, ip, "procedure_prescription")
    # plain-text summaries for our own text fields (NEVER assign a list here)
    if ip.meta.has_field("custom_primary_diagnosis"):
        ip.custom_primary_diagnosis = _rows_to_text(ea.get("diagnosis"),
                                                    ("diagnosis",))[:140]
    # a procedure ordered => this is a Surgery admission
    if ea.get("procedure_prescription"):
        ip.custom_care_type = "Surgery"
    if ip.meta.has_field("scheduled_date"):
        ip.scheduled_date = nowdate()
    ip.flags.ignore_mandatory = True
    ip.insert(ignore_permissions=True)

    ea.db_set("inpatient_record", ip.name)
    # link any invoices already raised from this emergency sheet to the new record
    _backfill_emergency_invoices(ea, ip.name)
    refresh_inpatient_billing_summary(ip.name)
    return ip.name


def _backfill_emergency_invoices(ea, inpatient_record):
    """Point invoices raised from the Emergency sheet at the new Inpatient Record,
    so their charges join the patient's inpatient balance."""
    row_ids = []
    for tf, dt in (("drug_prescription", "Drug Prescription"),
                   ("lab_test_prescription", "Lab Prescription"),
                   ("procedure_prescription", "Procedure Prescription")):
        for r in (ea.get(tf) or []):
            row_ids.append("{0}:{1}".format(dt, r.name))
    if not row_ids:
        return
    try:
        sis = frappe.get_all("Sales Invoice Item",
            filters={"custom_service_charge_row_id": ["in", row_ids]},
            fields=["parent"], distinct=True, pluck="parent")
        for si in set(sis):
            if not frappe.db.get_value("Sales Invoice", si, "custom_inpatient_record"):
                frappe.db.set_value("Sales Invoice", si, "custom_inpatient_record",
                                    inpatient_record, update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "backfill_emergency_invoices")


def _rows_to_text(rows, fieldnames):
    """Flatten child rows to a comma string using the first available field."""
    if not rows:
        return ""
    out = []
    for r in rows:
        val = None
        for fn in fieldnames:
            val = r.get(fn)
            if val:
                break
        out.append(str(val)) if val else None
    return ", ".join(out)


def _copy_child(src, dst, fieldname):
    """Copy a child table from src to dst. Only touches real table fields, so a
    Table value can never be assigned to a Data/Small Text field."""
    if not src.get(fieldname):
        return
    df = dst.meta.get_field(fieldname)
    if not df or df.fieldtype not in ("Table", "Table MultiSelect"):
        return
    for row in src.get(fieldname):
        d = row.as_dict()
        for k in ("name", "parent", "parentfield", "parenttype", "idx",
                  "creation", "modified", "owner", "modified_by", "docstatus"):
            d.pop(k, None)
        dst.append(fieldname, d)


@frappe.whitelist()
def auto_bill_emergency(doc, method=None):
    """on_submit of Emergency Assessment Sheet: bill the prescribed drug/lab/
    procedure rows into a draft invoice, exactly like patient_patch bills the
    Patient Encounter."""
    bill_sheet_prescriptions(doc, method)


@frappe.whitelist()
def send_emergency_to_billing(emergency):
    """Bill the Emergency Assessment Sheet's orders as a draft invoice, exactly
    like a Patient Encounter (works even before admission)."""
    ea = frappe.get_doc("Emergency Assessment Sheet", emergency)
    rows = _collect_order_rows(ea)
    if not rows:
        frappe.throw(_("Nothing to bill: add lab tests, imaging, procedures or items first."))
    customer = get_customer(ea.patient)
    if not customer:
        frappe.throw(_("Patient {0} has no linked Customer.").format(ea.patient))
    settings = get_settings()

    inv = frappe.new_doc("Sales Invoice")
    inv.customer = customer
    inv.patient = ea.patient
    inv.company = settings.default_company or frappe.defaults.get_user_default("Company")
    inv.currency = settings.currency or "USD"
    inv.posting_date = nowdate()
    inv.due_date = nowdate()
    inv.custom_is_inpatient_service_invoice = 1
    if ea.get("inpatient_record"):
        inv.custom_inpatient_record = ea.inpatient_record
    inv.remarks = _("Emergency orders from {0}").format(ea.name)
    for r in rows:
        child = inv.append("items", {})
        child.item_code = r["item_code"]
        child.qty = r["qty"]
        if r["rate"]:
            child.rate = r["rate"]
        child.description = r["desc"]
        child.custom_service_charge_row_id = "{0}:{1}".format(r["row_dt"], r["row_name"])
    inv.set_missing_values()
    inv.calculate_taxes_and_totals()
    inv.insert(ignore_permissions=True)
    ea.db_set("sales_invoice", inv.name)
    return inv.name


@frappe.whitelist()
# ===========================================================================
# CENTRAL BILLING FROM THE INPATIENT RECORD'S NATIVE TABLES
#   drug_prescription / lab_test_prescription / procedure_prescription
#   Mirrors how a consultation is billed. Idempotent: rows already flagged
#   billed are skipped, so nothing another app invoiced is double-billed.
# ===========================================================================
def _item_for_drug(row):
    code = row.get("drug_code") or row.get("medication")
    if code and frappe.db.exists("Item", code):
        return code
    med = row.get("medication")
    if med:
        it = frappe.db.get_value("Medication", med, "item") \
            or frappe.db.get_value("Medication", med, "item_code")
        if it:
            return it
    return None


def _item_for_lab(row):
    tmpl = row.get("lab_test_code") or row.get("lab_test_name")
    if tmpl:
        it = frappe.db.get_value("Lab Test Template", tmpl, "item")
        if it:
            return it
    return None


def _item_for_procedure(row):
    tmpl = row.get("procedure") or row.get("procedure_name")
    if tmpl:
        it = frappe.db.get_value("Clinical Procedure Template", tmpl, "item")
        if it:
            return it
    return None


def _sheet_prescription_rows(doc):
    """Unbilled billable rows from a sheet's native prescription tables."""
    rows = []
    for r in (doc.get("drug_prescription") or []):
        if cint(r.get("custom_is_billed")) or cint(r.get("invoiced")):
            continue
        item = _item_for_drug(r)
        if item:
            rows.append(("Drug Prescription", r, item,
                         r.get("drug_name") or r.get("drug_code"),
                         r.get("drug_code") or r.get("medication")))
    for r in (doc.get("lab_test_prescription") or []):
        if cint(r.get("invoiced")):
            continue
        item = _item_for_lab(r)
        if item:
            rows.append(("Lab Prescription", r, item,
                         r.get("lab_test_name") or r.get("lab_test_code"),
                         r.get("lab_test_code")))
    for r in (doc.get("procedure_prescription") or []):
        if cint(r.get("invoiced")):
            continue
        item = _item_for_procedure(r)
        if item:
            rows.append(("Procedure Prescription", r, item,
                         r.get("procedure_name") or r.get("procedure"),
                         r.get("procedure")))
    return rows


def _ir_row_item(dt, row):
    if dt == "Drug Prescription":
        return _item_for_drug(row)
    if dt == "Lab Prescription":
        return _item_for_lab(row)
    if dt == "Procedure Prescription":
        return _item_for_procedure(row)
    return None


def _mark_ir_row_invoiced(inpatient_record, dt, item_code, si_name, unset=False):
    """Mark (or unset) the matching Inpatient Record native prescription row.
    Matches by the RESOLVED item code (not raw code/name fields), so a row copied
    from the Emergency sheet is always found regardless of which field it used."""
    if not inpatient_record or not item_code:
        return
    tablefield = {"Drug Prescription": "drug_prescription",
                  "Lab Prescription": "lab_test_prescription",
                  "Procedure Prescription": "procedure_prescription"}.get(dt)
    if not tablefield:
        return
    want = cint(not unset)
    try:
        ip = frappe.get_doc("Inpatient Record", inpatient_record)
        for r in (ip.get(tablefield) or []):
            if _ir_row_item(dt, r) != item_code:
                continue
            already = cint(r.get("invoiced")) == want and (
                dt != "Drug Prescription" or cint(r.get("custom_is_billed")) == want)
            if not unset and already:
                continue  # find the next matching (e.g. duplicate) row
            if dt == "Drug Prescription":
                frappe.db.set_value(dt, r.name, {"custom_is_billed": want,
                    "custom_billed_sales_invoice": (None if unset else si_name)},
                    update_modified=False)
            if frappe.get_meta(dt).has_field("invoiced"):
                frappe.db.set_value(dt, r.name, "invoiced", want, update_modified=False)
            if not unset:
                break
    except Exception:
        frappe.log_error(frappe.get_traceback(), "mark_ir_row_invoiced")


def _new_presc_invoice(doc, kind):
    settings = get_settings()
    inv = frappe.new_doc("Sales Invoice")
    inv.customer = get_customer(doc.get("patient"))
    inv.patient = doc.get("patient")
    inv.company = settings.default_company or frappe.defaults.get_user_default("Company")
    inv.currency = settings.currency or "USD"
    inv.posting_date = nowdate()
    inv.due_date = nowdate()
    inv.custom_is_prescription_invoice = 1
    if doc.get("inpatient_record"):
        inv.custom_inpatient_record = doc.inpatient_record
    inv.remarks = _("{0} {1} ({2})").format(doc.doctype, doc.name, kind)
    return inv


def bill_sheet_prescriptions(doc, method=None):
    """ON SUBMIT of a prescribing sheet (Emergency Assessment Sheet, Daily Round
    Plan): create DRAFT Sales Invoices from the prescription tables. Drugs go to a
    SEPARATE pharmacy invoice; labs + procedures go to a services invoice. Rows are
    NOT marked invoiced here - that happens only when the invoice is submitted."""
    try:
        rows = _sheet_prescription_rows(doc)
        if not rows:
            return
        if not get_customer(doc.get("patient")):
            frappe.throw(_("Patient {0} has no linked Customer.").format(doc.get("patient")))

        drug_rows = [r for r in rows if r[0] == "Drug Prescription"]
        service_rows = [r for r in rows if r[0] != "Drug Prescription"]
        created = []

        for bucket, kind, flag in ((drug_rows, "Pharmacy", "custom_is_pharmacy_invoice"),
                                   (service_rows, "Services", "custom_is_service_invoice")):
            if not bucket:
                continue
            inv = _new_presc_invoice(doc, kind)
            inv.set(flag, 1)
            for dt, r, item, desc, match in bucket:
                child = inv.append("items", {})
                child.item_code = item
                child.qty = 1
                child.description = desc
                child.custom_service_charge_row_id = "{0}:{1}".format(dt, r.name)
            inv.set_missing_values()
            inv.calculate_taxes_and_totals()
            inv.insert(ignore_permissions=True)   # DRAFT - rows NOT yet invoiced
            created.append(inv.name)

        if doc.meta.has_field("sales_invoice") and created:
            doc.db_set("sales_invoice", created[0])
        if doc.get("inpatient_record"):
            refresh_inpatient_billing_summary(doc.inpatient_record)
        if created:
            frappe.msgprint(_("Draft invoice(s) created: {0}. Rows are marked invoiced "
                              "only when the invoice is submitted.").format(", ".join(created)))
    except frappe.ValidationError:
        raise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "bill_sheet_prescriptions")


def _mark_prescription_rows_invoiced(si, unset=False):
    """On SI submit (or cancel): mark the source sheet row, the matching Inpatient
    Record row, and (for procedures) the Clinical Procedure invoiced=1 (or 0).
    The IR row is matched by the invoice line's item_code (deterministic)."""
    ir = si.get("custom_inpatient_record")
    want = cint(not unset)
    for item in (si.get("items") or []):
        rid = item.get("custom_service_charge_row_id") or ""
        if ":" not in rid:
            continue
        dt, name = rid.split(":", 1)
        # 1) the sheet's own child row
        if frappe.db.exists(dt, name):
            if dt == "Drug Prescription":
                frappe.db.set_value(dt, name, {"custom_is_billed": want,
                    "custom_billed_sales_invoice": (None if unset else si.name)},
                    update_modified=False)
            if frappe.get_meta(dt).has_field("invoiced"):
                frappe.db.set_value(dt, name, "invoiced", want, update_modified=False)
        # 2) matching Inpatient Record row + Clinical Procedure, by item_code
        item_code = item.get("item_code")
        _mark_ir_row_invoiced(ir, dt, item_code, si.name, unset=unset)
        if dt == "Procedure Prescription":
            _mark_clinical_procedure_invoiced_by_item(ir, item_code, si.name, unset=unset)


def _mark_clinical_procedure_invoiced(inpatient_record, template, si_name, unset=False):
    """Set invoiced=1 (or 0) on the Clinical Procedure(s) for this template/admission."""
    if not inpatient_record or not template:
        return
    want = cint(not unset)
    try:
        for cp in frappe.get_all("Clinical Procedure",
                filters={"inpatient_record": inpatient_record, "procedure_template": template},
                pluck="name"):
            if frappe.get_meta("Clinical Procedure").has_field("invoiced"):
                frappe.db.set_value("Clinical Procedure", cp, "invoiced", want,
                                    update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "mark_clinical_procedure_invoiced")


def _mark_clinical_procedure_invoiced_by_item(inpatient_record, item_code, si_name, unset=False):
    """Mark Clinical Procedure(s) invoiced by matching the template's item_code."""
    if not inpatient_record or not item_code:
        return
    templates = frappe.get_all("Clinical Procedure Template",
        filters={"item": item_code}, pluck="name")
    for t in templates:
        _mark_clinical_procedure_invoiced(inpatient_record, t, si_name, unset=unset)


@frappe.whitelist()
def bill_inpatient_record(inpatient_record):
    """Prescription billing (drugs/labs/procedures) is handled by the patient_patch
    app now, so inpatient_patch no longer creates these invoices."""
    frappe.msgprint(_("Drug / Lab / Procedure billing is handled from the Patient "
                      "Encounter (patient_patch). Nothing to bill here."))
    return None


def assert_no_draft_invoices(inpatient_record, step=""):
    """Block a clinical step while any inpatient invoice is still DRAFT."""
    drafts = frappe.get_all("Sales Invoice",
        filters={"custom_inpatient_record": inpatient_record, "docstatus": 0},
        pluck="name")
    if drafts:
        frappe.throw(_("Cannot proceed{0}: invoice(s) {1} are still DRAFT. "
                       "Please go to <b>Reception / Pharmacy</b> and submit them first.")
                     .format((" with " + step) if step else "", ", ".join(drafts)))


def _reconcile_procedures_invoiced(inpatient_record):
    """For each IR procedure_prescription row not yet invoiced, check whether a
    SUBMITTED Sales Invoice (linked to this admission OR to its Patient Encounter)
    already contains that procedure's item. If so, mark the row invoiced=1. This
    covers procedures billed from the Patient Encounter by patient_patch."""
    try:
        ip = frappe.get_doc("Inpatient Record", inpatient_record)
    except Exception:
        return
    rows = [r for r in (ip.get("procedure_prescription") or []) if not cint(r.get("invoiced"))]
    if not rows:
        return
    # candidate submitted invoices: by inpatient record or by linked encounter
    inv_names = set(frappe.get_all("Sales Invoice",
        filters={"custom_inpatient_record": inpatient_record, "docstatus": 1}, pluck="name"))
    meta_si = frappe.get_meta("Sales Invoice")
    if meta_si.has_field("custom_patient_encounter"):
        for enc in _encounters_for(inpatient_record):
            inv_names |= set(frappe.get_all("Sales Invoice",
                filters={"custom_patient_encounter": enc, "docstatus": 1}, pluck="name"))
    if not inv_names:
        return
    billed_items = set()
    for si in inv_names:
        for it in frappe.get_all("Sales Invoice Item",
                filters={"parent": si}, pluck="item_code"):
            billed_items.add(it)
    for r in rows:
        item = _item_for_procedure(r)
        if item and item in billed_items:
            if frappe.get_meta("Procedure Prescription").has_field("invoiced"):
                frappe.db.set_value("Procedure Prescription", r.name, "invoiced", 1,
                                    update_modified=False)
            _mark_clinical_procedure_invoiced(inpatient_record, r.get("procedure"), None)


@frappe.whitelist()
def create_procedures_from_record(inpatient_record):
    """Create a Clinical Procedure from each INVOICED procedure_prescription row's
    template. Blocks if the anaesthetist marked the patient Unfit, if pre-op is not
    ready, or if the procedure has not been invoiced (submitted) yet."""
    ip = frappe.get_doc("Inpatient Record", inpatient_record)
    if _anesthesia_unfit(inpatient_record):
        frappe.throw(_("Patient is <b>UNFIT for operation</b> (Pre-Anaesthetic "
                       "Assessment). The operation cannot proceed."))
    if _cardiac_not_cleared(inpatient_record):
        frappe.throw(_("Cardiac Review is <b>not cleared</b> (plan is not 'Fit for "
                       "Surgery'). The operation cannot proceed."))
    from inpatient_patch.inpatient_patch.ot import _preop_blockers
    missing = _preop_blockers(inpatient_record)
    if missing:
        frappe.throw(_("Pre-op not ready \u2014 finish first: {0}.").format(", ".join(missing)))
    # pick up procedures already billed via the Patient Encounter / admission SI
    _reconcile_procedures_invoiced(inpatient_record)
    made = []
    any_row = False
    for r in (ip.get("procedure_prescription") or []):
        any_row = True
        if cint(r.get("procedure_created")):
            continue
        if not cint(r.get("invoiced")):
            continue  # must be invoiced (submitted) before we create the procedure
        tmpl = r.get("procedure")
        if not tmpl or not frappe.db.exists("Clinical Procedure Template", tmpl):
            continue
        cp = frappe.new_doc("Clinical Procedure")
        cp.patient = ip.patient
        cp.procedure_template = tmpl
        cp.company = _company(ip.as_dict())
        if cp.meta.has_field("inpatient_record"):
            cp.inpatient_record = ip.name
        if cp.meta.has_field("medical_department") and r.get("department"):
            cp.medical_department = r.get("department")
        cp.flags.ignore_mandatory = True
        cp.insert(ignore_permissions=True)
        # auto-load the stock consumption defined on the template
        try:
            if hasattr(cp, "set_actual_qty"):
                cp.reload()
        except Exception:
            pass
        frappe.db.set_value("Procedure Prescription", r.name, "procedure_created", 1,
                            update_modified=False)
        made.append(cp.name)
    if made:
        frappe.msgprint(_("Created Clinical Procedure(s): {0}").format(", ".join(made)))
    elif any_row:
        frappe.throw(_("No procedure has a <b>submitted invoice</b> yet. The patient "
                       "must be invoiced (invoice submitted) before the operation."))
    else:
        frappe.msgprint(_("No procedures ordered."))
    return made


def _anesthesia_unfit(inpatient_record):
    """True if the latest Pre Anesthetic Assessment marks the patient Unfit."""
    row = frappe.get_all("Pre Anesthetic Assessment",
        filters={"inpatient_record": inpatient_record},
        fields=["fitness"], order_by="modified desc", limit=1)
    return bool(row and (row[0].fitness or "").lower().startswith("unfit"))


def _cardiac_not_cleared(inpatient_record):
    """True if a Cardiac Review exists but its plan is not 'Fit for Surgery'."""
    row = frappe.get_all("Pre Operation Cardiac Review",
        filters={"inpatient_record": inpatient_record},
        fields=["plan"], order_by="modified desc", limit=1)
    return bool(row and (row[0].plan or "") not in ("", "Fit for Surgery"))


def on_submit_service_order(doc, method=None):
    """Auto-create the draft invoice when a service order is submitted (no button)."""
    try:
        send_service_order_to_billing(doc.name)
    except frappe.ValidationError:
        raise
    except Exception:
        frappe.log_error(frappe.get_traceback(), "on_submit_service_order")


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


def _encounters_for(inpatient_record):
    """Patient Encounters linked to this admission (by our link, else by patient)."""
    names = frappe.get_all("Patient Encounter",
        filters={"custom_inpatient_record": inpatient_record}, pluck="name")
    if names:
        return names
    patient = frappe.db.get_value("Inpatient Record", inpatient_record, "patient")
    if not patient:
        return []
    return frappe.get_all("Patient Encounter", filters={"patient": patient},
                          order_by="creation desc", pluck="name", limit=5)


@frappe.whitelist()
def pull_encounter_orders(inpatient_record):
    """Mirror the doctor's Patient Encounter orders into the service order tables."""
    out = {"lab_tests": [], "imaging": [], "procedures": [], "items": []}
    for enc in _encounters_for(inpatient_record):
        doc = frappe.get_doc("Patient Encounter", enc)
        for r in (doc.get("lab_test_prescription") or []):
            tmpl = r.get("lab_test_code")
            if tmpl:
                out["lab_tests"].append({"lab_test_template": tmpl,
                                         "lab_test_name": r.get("lab_test_name"), "qty": 1})
        for r in (doc.get("procedure_prescription") or []):
            tmpl = r.get("procedure")
            if tmpl:
                out["procedures"].append({"procedure_template": tmpl,
                                          "procedure_name": r.get("procedure_name"), "qty": 1})
        for r in (doc.get("drug_prescription") or []):
            code = r.get("drug_code") or r.get("medication")
            if code and frappe.db.exists("Item", code):
                out["items"].append({"item_code": code,
                                     "item_name": r.get("drug_name"), "qty": 1})
    return out


@frappe.whitelist()
def pull_prescribed_medicines(inpatient_record):
    """Medicines to administer, pulled from the Inpatient Record's own drug list,
    the Daily Round Plans, and any encounter - so the MAR reflects everything the
    doctor prescribed for this admission."""
    out = []
    seen = set()

    def _add(rows):
        for r in (rows or []):
            code = r.get("drug_code") or r.get("medication")
            key = (code or "", r.get("drug_name") or "", r.get("dosage") or "")
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "drug_code": code if (code and frappe.db.exists("Item", code)) else None,
                "drug_name": r.get("drug_name"),
                "dose": r.get("dosage"), "status": "Pending"})

    # 1) Inpatient Record native drug list
    try:
        ip = frappe.get_doc("Inpatient Record", inpatient_record)
        _add(ip.get("drug_prescription"))
    except Exception:
        pass
    # 2) Daily Round Plans for this admission
    for rp in frappe.get_all("Daily Round Plan",
            filters={"inpatient_record": inpatient_record, "docstatus": ["!=", 2]},
            pluck="name"):
        try:
            _add(frappe.get_doc("Daily Round Plan", rp).get("drug_prescription"))
        except Exception:
            pass
    # 3) encounters (fallback / consultation)
    for enc in _encounters_for(inpatient_record):
        try:
            _add(frappe.get_doc("Patient Encounter", enc).get("drug_prescription"))
        except Exception:
            pass
    return out


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
    """When an inpatient invoice is submitted, mark app-owned source rows billed
    and refresh the record summary. Prescription tables (Drug/Lab/Procedure) are
    billed by patient_patch, not here, so they are left untouched."""
    # service order rows (row id stored as "RowDocType:RowName") - app-owned tables
    if cint(getattr(doc, "custom_is_inpatient_service_invoice", 0)):
        for item in doc.items:
            row_id = item.get("custom_service_charge_row_id") or ""
            if ":" in row_id:
                row_dt, _sep, row_name = row_id.partition(":")
                # only our own service-order child tables carry a 'billed' column
                if (row_name and frappe.db.exists(row_dt, row_name)
                        and frappe.get_meta(row_dt).has_field("billed")):
                    frappe.db.set_value(row_dt, row_name,
                                        {"billed": 1, "billed_invoice": doc.name},
                                        update_modified=False)
        if doc.get("custom_inpatient_service_order"):
            _refresh_service_order_status(doc.custom_inpatient_service_order)

    # OT consumable rows
    if cint(getattr(doc, "custom_is_consumable_invoice", 0)):
        for item in doc.items:
            row_id = item.get("custom_ot_consumable_row_id")
            if (row_id and frappe.db.exists("OT Consumable Line", row_id)
                    and frappe.get_meta("OT Consumable Line").has_field("billed")):
                frappe.db.set_value("OT Consumable Line", row_id,
                                    {"billed": 1, "billed_invoice": doc.name},
                                    update_modified=False)

    # prescription invoices (Emergency / Daily Round Plan): mark rows invoiced now
    if cint(getattr(doc, "custom_is_prescription_invoice", 0)):
        _mark_prescription_rows_invoiced(doc)

    if doc.get("custom_inpatient_record"):
        refresh_inpatient_billing_summary(doc.custom_inpatient_record)


def on_cancel_sales_invoice(doc, method=None):
    # reverse prescription flags (sheet rows, IR rows, Clinical Procedure)
    if cint(getattr(doc, "custom_is_prescription_invoice", 0)):
        _mark_prescription_rows_invoiced(doc, unset=True)
    # reverse service-order row flags
    if cint(getattr(doc, "custom_is_inpatient_service_invoice", 0)):
        for item in (doc.get("items") or []):
            rid = item.get("custom_service_charge_row_id") or ""
            if ":" in rid:
                row_dt, _sep, row_name = rid.partition(":")
                if (row_name and frappe.db.exists(row_dt, row_name)
                        and frappe.get_meta(row_dt).has_field("billed")):
                    frappe.db.set_value(row_dt, row_name,
                                        {"billed": 0, "billed_invoice": None},
                                        update_modified=False)
    # reverse OT consumable flags
    if cint(getattr(doc, "custom_is_consumable_invoice", 0)):
        for item in (doc.get("items") or []):
            row_id = item.get("custom_ot_consumable_row_id")
            if (row_id and frappe.db.exists("OT Consumable Line", row_id)
                    and frappe.get_meta("OT Consumable Line").has_field("billed")):
                frappe.db.set_value("OT Consumable Line", row_id,
                                    {"billed": 0, "billed_invoice": None},
                                    update_modified=False)
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
    allrows = (list(so.get("lab_tests") or []) + list(so.get("imaging") or [])
               + list(so.get("procedures") or []) + list(so.get("items") or []))
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
    company_currency = frappe.get_cached_value("Company", company, "default_currency")

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

    # ---- accounts (fixes 'paid_to / paid_to_account_currency mandatory') ----
    # paid_from = the customer's receivable account
    try:
        from erpnext.accounts.party import get_party_account
        paid_from = get_party_account("Customer", customer, company)
    except Exception:
        paid_from = frappe.get_cached_value("Company", company, "default_receivable_account")
    # paid_to = chosen deposit account > settings > mode-of-payment default > cash
    paid_to = doc.get("deposit_to_account") or settings.get("deposit_account")
    if not paid_to and pe.mode_of_payment:
        paid_to = frappe.db.get_value("Mode of Payment Account",
            {"parent": pe.mode_of_payment, "company": company}, "default_account")
    if not paid_to:
        paid_to = (frappe.get_cached_value("Company", company, "default_cash_account")
                   or frappe.get_cached_value("Company", company, "default_bank_account"))
    if not paid_from or not paid_to:
        frappe.throw(_("Set a Deposit / Advance Account in Inpatient Billing Settings "
                       "(or a default cash account on the company)."))

    pe.paid_from = paid_from
    pe.paid_to = paid_to
    pe.paid_from_account_currency = (frappe.db.get_value("Account", paid_from,
                                     "account_currency") or company_currency)
    pe.paid_to_account_currency = (frappe.db.get_value("Account", paid_to,
                                   "account_currency") or company_currency)
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1

    # ---- auto-reconcile: allocate against this admission's unpaid invoices ----
    try:
        unpaid = frappe.get_all("Sales Invoice",
            filters={"custom_inpatient_record": doc.inpatient_record, "docstatus": 1,
                     "outstanding_amount": [">", 0]},
            fields=["name", "outstanding_amount"], order_by="posting_date asc")
        remaining = flt(doc.amount)
        for inv in unpaid:
            if remaining <= 0:
                break
            alloc = min(remaining, flt(inv.outstanding_amount))
            pe.append("references", {
                "reference_doctype": "Sales Invoice",
                "reference_name": inv.name,
                "allocated_amount": alloc,
            })
            remaining -= alloc
        if pe.get("references"):
            pe.set_amounts()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "deposit auto-reconcile")

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
def _refresh_ir_from_payment(pe):
    """Refresh the billing summary of every Inpatient Record touched by this
    Payment Entry's referenced Sales Invoices."""
    seen = set()
    for ref in (pe.get("references") or []):
        if ref.get("reference_doctype") == "Sales Invoice" and ref.get("reference_name"):
            ir = frappe.db.get_value("Sales Invoice", ref.reference_name,
                                     "custom_inpatient_record")
            if ir and ir not in seen:
                seen.add(ir)
                refresh_inpatient_billing_summary(ir)


def on_submit_payment_entry(doc, method=None):
    _refresh_ir_from_payment(doc)


def on_cancel_payment_entry(doc, method=None):
    _refresh_ir_from_payment(doc)


def _sheet_of_invoice(si):
    """Return (doctype, name) of the prescribing sheet behind a prescription
    invoice, by reading the first tagged item row."""
    for item in (si.get("items") or []):
        rid = item.get("custom_service_charge_row_id") or ""
        if ":" in rid:
            dt, name = rid.split(":", 1)
            if frappe.db.exists(dt, name):
                parent = frappe.db.get_value(dt, name, ["parenttype", "parent"], as_dict=True)
                if parent and parent.parenttype in ("Emergency Assessment Sheet", "Daily Round Plan"):
                    return parent.parenttype, parent.parent
    return None, None


def before_cancel_sales_invoice(doc, method=None):
    """Do not allow a prescription invoice to be cancelled on its own while its
    source sheet is still submitted. The reversal must happen by cancelling the
    Emergency Assessment Sheet / Daily Round Plan, which rolls back every flag."""
    if not cint(getattr(doc, "custom_is_prescription_invoice", 0)):
        return
    dt, name = _sheet_of_invoice(doc)
    if dt and name and cint(frappe.db.get_value(dt, name, "docstatus")) == 1:
        frappe.throw(_("This invoice is linked to a submitted <b>{0}</b> ({1}). "
                       "To reverse the billing, cancel that {0} \u2014 it will roll back "
                       "all invoiced/billed flags automatically.").format(dt, name))


def cancel_sheet_invoices(doc, method=None):
    """on_cancel of a prescribing sheet: cancel/delete its invoices, which reverses
    all invoiced/billed flags on the sheet, the Inpatient Record and Clinical
    Procedures via on_cancel_sales_invoice."""
    row_ids = []
    for tf, dt in (("drug_prescription", "Drug Prescription"),
                   ("lab_test_prescription", "Lab Prescription"),
                   ("procedure_prescription", "Procedure Prescription")):
        for r in (doc.get(tf) or []):
            row_ids.append("{0}:{1}".format(dt, r.name))
    if not row_ids:
        return
    try:
        sis = set(frappe.get_all("Sales Invoice Item",
            filters={"custom_service_charge_row_id": ["in", row_ids]},
            distinct=True, pluck="parent"))
        for si in sis:
            si_doc = frappe.get_doc("Sales Invoice", si)
            if si_doc.docstatus == 1:
                si_doc.flags.ignore_permissions = True
                si_doc.cancel()   # triggers on_cancel_sales_invoice -> flags to 0
            elif si_doc.docstatus == 0:
                _mark_prescription_rows_invoiced(si_doc, unset=True)
                si_doc.delete(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "cancel_sheet_invoices")


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

        # A deposit is a Payment Entry that is auto-reconciled against the
        # patient's invoices, so `paid` (billed - outstanding) ALREADY includes
        # it. Outstanding must therefore be the raw invoice outstanding and must
        # NOT subtract the deposit again (that was the double-deduction bug).
        # Any deposit not yet applied to an invoice is a credit/advance and is
        # shown for information only.
        unapplied_deposit = max(deposit - paid, 0)
        frappe.db.set_value("Inpatient Record", name, {
            "custom_total_billed": total_billed,
            "custom_total_paid": paid,
            "custom_total_deposit": deposit,
            "custom_outstanding": max(outstanding - unapplied_deposit, 0),
        }, update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Inpatient billing summary refresh")
