# Copyright (c) 2026, Dagaar
import frappe


def after_install():
    """Seed the billing settings + a few example department protocols so the
    app is usable immediately. Safe & idempotent."""
    _seed_settings()
    _seed_protocols()
    _seed_ot_facilities()
    frappe.db.commit()


def _seed_ot_facilities():
    """Create an unbillable 'Operating Theatre' service-unit type + two theatres."""
    try:
        ut = "Operating Theatre"
        if not frappe.db.exists("Healthcare Service Unit Type", ut):
            d = frappe.get_doc({
                "doctype": "Healthcare Service Unit Type",
                "service_unit_type": ut, "is_billable": 0,
                "inpatient_occupancy": 0, "allow_appointments": 0,
            })
            d.flags.ignore_mandatory = True
            d.insert(ignore_permissions=True)
        try:
            frappe.db.set_value("Healthcare Service Unit Type", ut,
                                "custom_is_ot_facility", 1)
        except Exception:
            pass

        company = (frappe.db.get_single_value("Inpatient Billing Settings",
                                              "default_company")
                   or frappe.defaults.get_global_default("company")
                   or frappe.db.get_value("Company", {}, "name"))
        if not company:
            return
        for name in ("Operating Theatre 1", "Operating Theatre 2"):
            if frappe.db.exists("Healthcare Service Unit",
                                {"healthcare_service_unit_name": name}):
                continue
            try:
                su = frappe.get_doc({
                    "doctype": "Healthcare Service Unit",
                    "healthcare_service_unit_name": name,
                    "service_unit_type": ut, "company": company, "is_group": 0,
                    "inpatient_occupancy": 0,
                })
                su.flags.ignore_mandatory = True
                su.insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "seed OT unit")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "seed OT facilities")


def _seed_settings():
    s = frappe.get_single("Inpatient Billing Settings")
    if not s.currency:
        s.currency = "USD"
    if not s.daily_run_hour:
        s.daily_run_hour = 12
    s.auto_bed_billing_enabled = 1
    s.consolidate_bed_invoice = 1
    s.save(ignore_permissions=True)


EXAMPLE_PROTOCOLS = {
    "Orthopedic": {
        "is_surgical": 1,
        "forms": [
            ("Emergency", "Emergency Assessment Sheet", 1, 1),
            ("Admission", "Admission Social Data", 1, 2),
            ("Admission", "Nursing Admission Assessment", 1, 3),
            ("Admission", "History Clinical Examination", 1, 4),
            ("Ward", "Daily Round Plan", 0, 5),
            ("Pre-Operation", "Pre Operation Cardiac Review", 0, 6),
            ("Pre-Operation", "Pre Anesthetic Assessment", 1, 7),
            ("Pre-Operation", "Pre Operative Checklist", 1, 8),
            ("Pre-Operation", "Surgical Consent Form", 1, 9),
            ("Operation", "Operation Theatre Case", 1, 10),
            ("Operation", "Surgical Safety Checklist", 1, 11),
            ("Operation", "Operation Procedure Note", 1, 12),
            ("Recovery", "Recovery Nurse Record", 1, 13),
            ("Discharge", "Discharge Summary", 1, 14),
        ],
        "orders": [("Implant", None, "Orthopedic Screw Set", 1, "Confirm size in theatre"),
                   ("Drug", None, "Ceftriaxone 1g", 1, "Pre-op prophylaxis")],
    },
    "Pediatrics": {
        "is_surgical": 0,
        "forms": [
            ("Emergency", "Emergency Assessment Sheet", 1, 1),
            ("Admission", "Admission Social Data", 1, 2),
            ("Admission", "Nursing Admission Assessment", 1, 3),
            ("Admission", "History Clinical Examination", 1, 4),
            ("Ward", "Daily Round Plan", 1, 5),
            ("Ward", "Medication Administration Record", 1, 6),
            ("Discharge", "Discharge Summary", 1, 7),
        ],
        "orders": [("Nursing Task", None, "Weight-based dosing review", 1, "")],
    },
    "Obstetrics & Gynecology": {
        "is_surgical": 1,
        "forms": [
            ("Admission", "Admission Social Data", 1, 1),
            ("Admission", "Nursing Admission Assessment", 1, 2),
            ("Admission", "History Clinical Examination", 1, 3),
            ("Ward", "Daily Round Plan", 1, 4),
            ("Pre-Operation", "Pre Anesthetic Assessment", 1, 5),
            ("Pre-Operation", "Pre Operative Checklist", 1, 6),
            ("Pre-Operation", "Surgical Consent Form", 1, 7),
            ("Operation", "Operation Theatre Case", 1, 8),
            ("Operation", "Surgical Safety Checklist", 1, 9),
            ("Operation", "Operation Procedure Note", 1, 10),
            ("Recovery", "Recovery Nurse Record", 1, 11),
            ("Discharge", "Discharge Summary", 1, 12),
        ],
        "orders": [],
    },
    "Internal Medicine": {
        "is_surgical": 0,
        "forms": [
            ("Emergency", "Emergency Assessment Sheet", 1, 1),
            ("Admission", "Admission Social Data", 1, 2),
            ("Admission", "Nursing Admission Assessment", 1, 3),
            ("Admission", "History Clinical Examination", 1, 4),
            ("Ward", "Daily Round Plan", 1, 5),
            ("Ward", "Doctor Order", 1, 6),
            ("Ward", "Medication Administration Record", 1, 7),
            ("Ward", "Diabetic Insulin Chart", 0, 8),
            ("Discharge", "Discharge Summary", 1, 9),
        ],
        "orders": [],
    },
}


def _seed_protocols():
    for dept, cfg in EXAMPLE_PROTOCOLS.items():
        if not frappe.db.exists("Medical Department", dept):
            try:
                frappe.get_doc({"doctype": "Medical Department",
                                "department": dept}).insert(ignore_permissions=True)
            except Exception:
                continue
        if frappe.db.exists("Department Admission Protocol", dept):
            continue
        doc = frappe.new_doc("Department Admission Protocol")
        doc.medical_department = dept
        doc.enabled = 1
        doc.is_surgical = cfg["is_surgical"]
        doc.description = f"Example {dept} admission protocol (edit freely)."
        for stage, form, mand, seq in cfg["forms"]:
            doc.append("required_forms", {"stage": stage, "form": form,
                                          "mandatory": mand, "sequence": seq})
        for it, code, nm, qty, note in cfg["orders"]:
            doc.append("order_set", {"item_type": it, "item_code": code,
                                     "item_name": nm, "default_qty": qty, "notes": note})
        try:
            doc.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Seed protocol {dept}")
