# Copyright (c) 2026, Dagaar
"""
Idempotent custom-field installer.

Adds (never overwrites values) the fields this app needs on EXISTING healthcare
/ ERPNext doctypes. Safe to run repeatedly (after_install + after_migrate).
Mirrors the upsert approach used in patient_patch so the two apps coexist.
"""
import frappe


FIELD_CONFIGS = [
    # ---------------- Inpatient Record : department + workflow + billing ---
    {"dt": "Inpatient Record", "fieldname": "custom_ip_section",
     "fieldtype": "Section Break", "label": "Inpatient Suite"},
    {"dt": "Inpatient Record", "fieldname": "custom_medical_department",
     "fieldtype": "Link", "label": "Medical Department", "options": "Medical Department",
     "insert_after": "custom_ip_section"},
    {"dt": "Inpatient Record", "fieldname": "custom_care_type",
     "fieldtype": "Select", "label": "Care Type", "options": "Treatment\nSurgery",
     "default": "Treatment", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1,
     "description": "Surgery shows the OT steps; Treatment shows only nursing/inpatient steps. Can be changed during the stay.",
     "insert_after": "custom_medical_department"},
    {"dt": "Inpatient Record", "fieldname": "custom_admission_protocol",
     "fieldtype": "Link", "label": "Admission Protocol",
     "options": "Department Admission Protocol", "read_only": 1,
     "insert_after": "custom_care_type"},
    {"dt": "Inpatient Record", "fieldname": "custom_is_surgical",
     "fieldtype": "Check", "label": "Surgical Admission",
     "fetch_from": "custom_admission_protocol.is_surgical", "read_only": 1,
     "insert_after": "custom_admission_protocol"},
    {"dt": "Inpatient Record", "fieldname": "custom_current_bed",
     "fieldtype": "Link", "label": "Current Bed", "options": "Healthcare Service Unit",
     "read_only": 1, "insert_after": "custom_is_surgical"},

    {"dt": "Inpatient Record", "fieldname": "custom_workflow_cb",
     "fieldtype": "Column Break", "insert_after": "custom_current_bed"},
    {"dt": "Inpatient Record", "fieldname": "custom_emergency_done",
     "fieldtype": "Check", "label": "Emergency Assessment Done",
     "insert_after": "custom_workflow_cb"},
    {"dt": "Inpatient Record", "fieldname": "custom_nursing_assessment_done",
     "fieldtype": "Check", "label": "Nursing Assessment Done",
     "insert_after": "custom_emergency_done"},
    {"dt": "Inpatient Record", "fieldname": "custom_history_exam_done",
     "fieldtype": "Check", "label": "History & Exam Done",
     "insert_after": "custom_nursing_assessment_done"},
    {"dt": "Inpatient Record", "fieldname": "custom_preop_ready",
     "fieldtype": "Check", "label": "Pre-Op Ready",
     "insert_after": "custom_history_exam_done"},
    {"dt": "Inpatient Record", "fieldname": "custom_operated",
     "fieldtype": "Check", "label": "Operated",
     "insert_after": "custom_preop_ready"},
    {"dt": "Inpatient Record", "fieldname": "custom_discharge_ready",
     "fieldtype": "Check", "label": "Discharge Ready",
     "insert_after": "custom_operated"},

    # billing rollups
    {"dt": "Inpatient Record", "fieldname": "custom_billing_section",
     "fieldtype": "Section Break", "label": "Billing Summary",
     "insert_after": "custom_discharge_ready", "collapsible": 1},
    {"dt": "Inpatient Record", "fieldname": "custom_total_billed",
     "fieldtype": "Currency", "label": "Total Billed", "read_only": 1,
     "insert_after": "custom_billing_section"},
    {"dt": "Inpatient Record", "fieldname": "custom_total_paid",
     "fieldtype": "Currency", "label": "Total Paid", "read_only": 1,
     "insert_after": "custom_total_billed"},
    {"dt": "Inpatient Record", "fieldname": "custom_total_deposit",
     "fieldtype": "Currency", "label": "Total Deposit", "read_only": 1,
     "insert_after": "custom_total_paid"},
    {"dt": "Inpatient Record", "fieldname": "custom_billing_cb",
     "fieldtype": "Column Break", "insert_after": "custom_total_deposit"},
    {"dt": "Inpatient Record", "fieldname": "custom_outstanding",
     "fieldtype": "Currency", "label": "Outstanding", "read_only": 1,
     "insert_after": "custom_billing_cb"},
    {"dt": "Inpatient Record", "fieldname": "custom_last_bed_billed_date",
     "fieldtype": "Date", "label": "Last Bed Billed Date", "read_only": 1,
     "insert_after": "custom_outstanding"},

    # ---------------- Patient Encounter : inpatient link ------------------
    {"dt": "Patient Encounter", "fieldname": "custom_inpatient_record",
     "fieldtype": "Link", "label": "Inpatient Record", "options": "Inpatient Record"},

    # ---------------- Drug Prescription : inpatient / MAR -----------------
    {"dt": "Drug Prescription", "fieldname": "custom_inpatient_record",
     "fieldtype": "Link", "label": "Inpatient Record", "options": "Inpatient Record"},
    {"dt": "Drug Prescription", "fieldname": "custom_administer_via_mar",
     "fieldtype": "Check", "label": "Administer via MAR"},

    # ---------------- Sales Invoice : inpatient tagging -------------------
    {"dt": "Sales Invoice", "fieldname": "custom_inpatient_record",
     "fieldtype": "Link", "label": "Inpatient Record", "options": "Inpatient Record",
     "read_only": 1, "allow_on_submit": 1},
    {"dt": "Sales Invoice", "fieldname": "custom_is_inpatient_bed_invoice",
     "fieldtype": "Check", "label": "Inpatient Bed Invoice", "read_only": 1,
     "allow_on_submit": 1},
    {"dt": "Sales Invoice", "fieldname": "custom_is_inpatient_service_invoice",
     "fieldtype": "Check", "label": "Inpatient Service Invoice", "read_only": 1,
     "allow_on_submit": 1},
    {"dt": "Sales Invoice", "fieldname": "custom_is_consumable_invoice",
     "fieldtype": "Check", "label": "OT Consumable Invoice", "read_only": 1,
     "allow_on_submit": 1},
    {"dt": "Sales Invoice", "fieldname": "custom_inpatient_service_order",
     "fieldtype": "Link", "label": "Inpatient Service Order",
     "options": "Inpatient Service Order", "read_only": 1, "allow_on_submit": 1},
    {"dt": "Sales Invoice", "fieldname": "custom_ot_case",
     "fieldtype": "Link", "label": "Operation Theatre Case",
     "options": "Operation Theatre Case", "read_only": 1, "allow_on_submit": 1},
    {"dt": "Sales Invoice", "fieldname": "custom_bed_billed_date",
     "fieldtype": "Date", "label": "Bed Billed Date", "read_only": 1,
     "allow_on_submit": 1},

    # ---------------- Sales Invoice Item : source tracing ----------------
    {"dt": "Sales Invoice Item", "fieldname": "custom_service_charge_row_id",
     "fieldtype": "Data", "label": "Service Charge Row ID", "read_only": 1,
     "allow_on_submit": 1},
    {"dt": "Sales Invoice Item", "fieldname": "custom_ot_consumable_row_id",
     "fieldtype": "Data", "label": "OT Consumable Row ID", "read_only": 1,
     "allow_on_submit": 1},
    {"dt": "Sales Invoice Item", "fieldname": "custom_inpatient_record",
     "fieldtype": "Link", "label": "Inpatient Record", "options": "Inpatient Record",
     "read_only": 1, "allow_on_submit": 1},

    # ---------------- Patient : age convenience (shared w/ patient_patch) -
    {"dt": "Patient", "fieldname": "custom_patient_age",
     "fieldtype": "Data", "label": "Patient Age"},
]


# Compatibility columns referenced by other apps / native dialogs but sometimes
# missing on a bench. Created if absent; never removed by our uninstall.
COMPAT_FIELDS = [
    {"dt": "Healthcare Service Unit", "fieldname": "custom_disabled",
     "fieldtype": "Check", "label": "Disabled", "default": "0",
     "insert_after": "service_unit_type"},
    {"dt": "Healthcare Service Unit Type", "fieldname": "custom_is_ot_facility",
     "fieldtype": "Check", "label": "OT Facility (unbillable theatre)",
     "insert_after": "is_billable"},
]


def _upsert(cfg):
    cf_name = f"{cfg['dt']}-{cfg['fieldname']}"
    if frappe.db.exists("Custom Field", cf_name):
        doc = frappe.get_doc("Custom Field", cf_name)
        old_type = doc.fieldtype
        for key, value in cfg.items():
            setattr(doc, key, value)
        # never silently change a field's type on an existing column
        doc.fieldtype = old_type
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc({"doctype": "Custom Field", **cfg}).insert(ignore_permissions=True)


def execute():
    for cfg in FIELD_CONFIGS:
        try:
            _upsert(cfg)
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             f"Inpatient Patch custom field: {cfg.get('fieldname')}")
    # Compatibility shims: some benches reference columns that other apps were
    # supposed to create (e.g. the native Admit dialog filters Healthcare Service
    # Unit by custom_disabled). Create them if missing so those queries don't 500.
    # These are NOT removed on uninstall (we don't own them).
    for cfg in COMPAT_FIELDS:
        try:
            if not frappe.db.exists("Custom Field", f"{cfg['dt']}-{cfg['fieldname']}"):
                frappe.get_doc({"doctype": "Custom Field", **cfg}).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             f"Inpatient Patch compat field: {cfg.get('fieldname')}")
    frappe.db.commit()
