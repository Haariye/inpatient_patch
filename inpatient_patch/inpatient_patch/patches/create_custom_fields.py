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
    {"dt": "Inpatient Record", "fieldname": "custom_care_type",
     "fieldtype": "Select", "label": "Care Type", "options": "Treatment\nSurgery",
     "default": "Treatment", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1,
     "allow_in_quick_entry": 1,
     "description": "Surgery shows the OT steps; Treatment shows only nursing/inpatient steps. Can be changed during the stay.",
     "insert_after": "custom_ip_section"},
    {"dt": "Inpatient Record", "fieldname": "custom_mode_of_admission",
     "fieldtype": "Select", "label": "Mode of Admission",
     "options": "\nElective\nEmergency\nReferral\nTransfer", "allow_in_quick_entry": 1,
     "in_standard_filter": 1, "insert_after": "custom_care_type"},
    {"dt": "Inpatient Record", "fieldname": "custom_admitting_doctor",
     "fieldtype": "Link", "label": "Admitting Doctor", "options": "Healthcare Practitioner",
     "fetch_from": "primary_practitioner", "insert_after": "custom_mode_of_admission"},
    {"dt": "Inpatient Record", "fieldname": "custom_responsible_nurse",
     "fieldtype": "Link", "label": "Responsible Nurse", "options": "Nurse",
     "insert_after": "custom_admitting_doctor"},
    {"dt": "Inpatient Record", "fieldname": "custom_primary_diagnosis",
     "fieldtype": "Data", "label": "Primary Diagnosis",
     "insert_after": "custom_responsible_nurse"},
    {"dt": "Inpatient Record", "fieldname": "custom_is_sponsored",
     "fieldtype": "Check", "label": "Sponsors (waive balance)",
     "description": "Waive the outstanding balance at discharge. Only allowed when the patient's Customer Group is NOT Patient/Patients.",
     "insert_after": "custom_primary_diagnosis"},
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
    # ---- Admission Social Data (was a separate doctype; now a section) ----
    {"dt": "Inpatient Record", "fieldname": "custom_social_sb",
     "fieldtype": "Section Break", "label": "Admission Social Data",
     "collapsible": 1, "insert_after": "custom_current_bed"},
    {"dt": "Inpatient Record", "fieldname": "custom_blood_group",
     "fieldtype": "Data", "label": "Blood Group", "fetch_from": "patient.blood_group",
     "read_only": 1, "insert_after": "custom_social_sb"},
    {"dt": "Inpatient Record", "fieldname": "custom_occupation",
     "fieldtype": "Data", "label": "Occupation", "insert_after": "custom_blood_group"},
    {"dt": "Inpatient Record", "fieldname": "custom_marital_status",
     "fieldtype": "Select", "label": "Marital Status",
     "options": "\nSingle\nMarried\nDivorced\nWidowed", "insert_after": "custom_occupation"},
    {"dt": "Inpatient Record", "fieldname": "custom_next_of_kin",
     "fieldtype": "Data", "label": "Next of Kin", "insert_after": "custom_marital_status"},
    {"dt": "Inpatient Record", "fieldname": "custom_next_of_kin_phone",
     "fieldtype": "Data", "label": "Next of Kin Phone", "insert_after": "custom_next_of_kin"},
    {"dt": "Inpatient Record", "fieldname": "custom_social_cb",
     "fieldtype": "Column Break", "insert_after": "custom_next_of_kin_phone"},
    {"dt": "Inpatient Record", "fieldname": "custom_allergies",
     "fieldtype": "Small Text", "label": "Allergies", "insert_after": "custom_social_cb"},
    {"dt": "Inpatient Record", "fieldname": "custom_chronic_conditions",
     "fieldtype": "Small Text", "label": "Chronic Conditions", "insert_after": "custom_allergies"},
    {"dt": "Inpatient Record", "fieldname": "custom_past_surgeries",
     "fieldtype": "Small Text", "label": "Past Surgeries", "insert_after": "custom_chronic_conditions"},
    {"dt": "Inpatient Record", "fieldname": "custom_current_medications",
     "fieldtype": "Small Text", "label": "Current Medications", "insert_after": "custom_past_surgeries"},

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

    # Patient Encounter has a NATIVE inpatient_record field, so we do NOT add a
    # custom one (retired to avoid duplicate fields).

    # ---------------- Drug Prescription : inpatient / MAR -----------------
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
     "fieldtype": "Link", "label": "Clinical Procedure",
     "options": "Clinical Procedure", "read_only": 1, "allow_on_submit": 1},
    {"dt": "Sales Invoice", "fieldname": "custom_is_prescription_invoice",
     "fieldtype": "Check", "label": "Is Prescription Invoice", "read_only": 1},
    {"dt": "Sales Invoice", "fieldname": "custom_is_pharmacy_invoice",
     "fieldtype": "Check", "label": "Is Pharmacy Invoice", "read_only": 1},
    {"dt": "Sales Invoice", "fieldname": "custom_is_service_invoice",
     "fieldtype": "Check", "label": "Is Service Invoice", "read_only": 1},
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

    # ============================================================= THEATRE
    # Clinical Procedure is the theatre core. These fields carry everything
    # the old Operation Theatre Case + OR Tracking Board used to hold.
    {"dt": "Clinical Procedure", "fieldname": "custom_theatre_sb",
     "fieldtype": "Section Break", "label": "Theatre / Operation",
     "insert_after": "medical_department"},
    {"dt": "Clinical Procedure", "fieldname": "custom_operation_theatre",
     "fieldtype": "Link", "label": "Operation Theatre", "options": "Healthcare Service Unit",
     "insert_after": "custom_theatre_sb"},
    {"dt": "Clinical Procedure", "fieldname": "custom_lead_surgeon",
     "fieldtype": "Link", "label": "Lead Surgeon", "options": "Healthcare Practitioner",
     "insert_after": "custom_operation_theatre"},
    {"dt": "Clinical Procedure", "fieldname": "custom_anesthesia_type",
     "fieldtype": "Select", "label": "Anaesthesia",
     "options": "\nGA (General)\nSA (Spinal)\nRegional Block\nLocal\nSedation\nOther",
     "insert_after": "custom_lead_surgeon"},
    {"dt": "Clinical Procedure", "fieldname": "custom_cb_theatre",
     "fieldtype": "Column Break", "insert_after": "custom_anesthesia_type"},
    {"dt": "Clinical Procedure", "fieldname": "custom_anesthetist",
     "fieldtype": "Link", "label": "Anaesthetist", "options": "Healthcare Practitioner",
     "insert_after": "custom_cb_theatre"},
    {"dt": "Clinical Procedure", "fieldname": "custom_scrub_nurse",
     "fieldtype": "Link", "label": "Scrub Nurse", "options": "Nurse",
     "insert_after": "custom_anesthetist"},
    {"dt": "Clinical Procedure", "fieldname": "custom_circulating_nurse",
     "fieldtype": "Link", "label": "Circulating Nurse", "options": "Nurse",
     "insert_after": "custom_scrub_nurse"},
    {"dt": "Clinical Procedure", "fieldname": "custom_team_sb",
     "fieldtype": "Section Break", "label": "Surgical Team",
     "insert_after": "custom_circulating_nurse"},
    {"dt": "Clinical Procedure", "fieldname": "custom_surgical_team",
     "fieldtype": "Table", "label": "Team Members", "options": "OT Team Member",
     "insert_after": "custom_team_sb"},
    {"dt": "Clinical Procedure", "fieldname": "custom_equip_sb",
     "fieldtype": "Section Break", "label": "Equipment", "collapsible": 1,
     "insert_after": "custom_surgical_team"},
    {"dt": "Clinical Procedure", "fieldname": "custom_cautery_used",
     "fieldtype": "Check", "label": "Cautery used", "insert_after": "custom_equip_sb"},
    {"dt": "Clinical Procedure", "fieldname": "custom_c_arm_used",
     "fieldtype": "Check", "label": "C-arm used", "insert_after": "custom_cautery_used"},
    {"dt": "Clinical Procedure", "fieldname": "custom_tourniquet_used",
     "fieldtype": "Check", "label": "Tourniquet used", "insert_after": "custom_c_arm_used"},
    {"dt": "Clinical Procedure", "fieldname": "custom_blood_loss_ml",
     "fieldtype": "Int", "label": "Estimated Blood Loss (ml)",
     "insert_after": "custom_tourniquet_used"},
    {"dt": "Clinical Procedure", "fieldname": "custom_track_sb",
     "fieldtype": "Section Break", "label": "OR Tracking (times)",
     "insert_after": "custom_blood_loss_ml"},
    {"dt": "Clinical Procedure", "fieldname": "custom_time_in",
     "fieldtype": "Datetime", "label": "Time In", "read_only": 1,
     "insert_after": "custom_track_sb"},
    {"dt": "Clinical Procedure", "fieldname": "custom_surgery_start",
     "fieldtype": "Datetime", "label": "Surgery Start", "read_only": 1,
     "insert_after": "custom_time_in"},
    {"dt": "Clinical Procedure", "fieldname": "custom_cb_track",
     "fieldtype": "Column Break", "insert_after": "custom_surgery_start"},
    {"dt": "Clinical Procedure", "fieldname": "custom_surgery_finish",
     "fieldtype": "Datetime", "label": "Surgery Finish", "read_only": 1,
     "insert_after": "custom_cb_track"},
    {"dt": "Clinical Procedure", "fieldname": "custom_time_out",
     "fieldtype": "Datetime", "label": "Time Out", "read_only": 1,
     "insert_after": "custom_surgery_finish"},
    {"dt": "Clinical Procedure", "fieldname": "custom_safety_sb",
     "fieldtype": "Section Break", "label": "Surgical Safety Checklist", "collapsible": 1,
     "insert_after": "custom_time_out"},
    {"dt": "Clinical Procedure", "fieldname": "custom_safety_signin",
     "fieldtype": "Check", "label": "Sign-In (before anaesthesia)",
     "insert_after": "custom_safety_sb"},
    {"dt": "Clinical Procedure", "fieldname": "custom_safety_timeout",
     "fieldtype": "Check", "label": "Time-Out (before incision)",
     "insert_after": "custom_safety_signin"},
    {"dt": "Clinical Procedure", "fieldname": "custom_safety_signout",
     "fieldtype": "Check", "label": "Sign-Out (before leaving)",
     "insert_after": "custom_safety_timeout"},
    {"dt": "Clinical Procedure", "fieldname": "custom_report_sb",
     "fieldtype": "Section Break", "label": "Operation Report",
     "insert_after": "custom_safety_signout"},
    {"dt": "Clinical Procedure", "fieldname": "custom_preop_diagnosis",
     "fieldtype": "Small Text", "label": "Pre-op Diagnosis",
     "insert_after": "custom_report_sb"},
    {"dt": "Clinical Procedure", "fieldname": "custom_postop_diagnosis",
     "fieldtype": "Small Text", "label": "Post-op Diagnosis",
     "insert_after": "custom_preop_diagnosis"},
    {"dt": "Clinical Procedure", "fieldname": "custom_procedure_performed",
     "fieldtype": "Small Text", "label": "Procedure Performed",
     "insert_after": "custom_postop_diagnosis"},
    {"dt": "Clinical Procedure", "fieldname": "custom_operation_note",
     "fieldtype": "Text", "label": "Operation Note",
     "insert_after": "custom_procedure_performed"},
    {"dt": "Clinical Procedure", "fieldname": "custom_findings",
     "fieldtype": "Text", "label": "Findings", "insert_after": "custom_operation_note"},
    {"dt": "Clinical Procedure", "fieldname": "custom_cb_report",
     "fieldtype": "Column Break", "insert_after": "custom_findings"},
    {"dt": "Clinical Procedure", "fieldname": "custom_drains",
     "fieldtype": "Data", "label": "Drains", "insert_after": "custom_cb_report"},
    {"dt": "Clinical Procedure", "fieldname": "custom_sponge_count_correct",
     "fieldtype": "Check", "label": "Sponge / Instrument Count Correct",
     "insert_after": "custom_drains"},
    {"dt": "Clinical Procedure", "fieldname": "custom_complications",
     "fieldtype": "Small Text", "label": "Complications",
     "insert_after": "custom_sponge_count_correct"},
    {"dt": "Clinical Procedure", "fieldname": "custom_surgery_report",
     "fieldtype": "Text", "label": "Surgery Report (generated)", "read_only": 1,
     "insert_after": "custom_complications"},
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


def force_sync_doctypes():
    """Re-import every DocType this app ships, ignoring the timestamp skip, so
    `bench migrate` ALWAYS (re)creates them. Prevents 'DocType X not found'."""
    import os
    from frappe.modules.import_file import import_file_by_path
    base = frappe.get_app_path("inpatient_patch", "inpatient_patch", "doctype")
    if not os.path.isdir(base):
        return
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d, d + ".json")
        if os.path.exists(p):
            try:
                import_file_by_path(p, force=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "force_sync %s" % d)
    frappe.db.commit()


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
