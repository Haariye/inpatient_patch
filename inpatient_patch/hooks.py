app_name = "inpatient_patch"
app_title = "Inpatient Patch"
app_publisher = "Dagaar"
app_description = "Comprehensive Inpatient, OT and Somali-billing extension for Frappe Healthcare v15"
app_email = "info.dagaar@gmail.com"
app_license = "mit"
required_apps = ["frappe/healthcare"]

# ---- assets ---------------------------------------------------------------
app_include_js = [
    "/assets/inpatient_patch/js/checkbox_children.js",
]

doctype_js = {
    "Inpatient Record": "public/js/inpatient_record_hub.js",
    "Inpatient Service Order": "public/js/service_order.js",
    "Clinical Procedure": "public/js/clinical_procedure.js",
    "Emergency Assessment Sheet": "public/js/emergency_assessment.js",
    "Nurse Handover": "public/js/nurse_handover.js",
    "Nurse Admission Assignment": "public/js/nurse_assignment.js",
    "Diabetic Insulin Chart": "public/js/nurse_defaults.js",
    "Medication Administration Record": "public/js/mar.js",
    "Pre Operative Checklist": "public/js/preop_checklist.js",
}

# ---- document events ------------------------------------------------------
override_doctype_dashboards = {
    "Inpatient Record": "inpatient_patch.inpatient_patch.dashboard_ip.get_dashboard_data",
}

# ---- row-level access: a Nurse only sees her assigned Inpatient Records ------
permission_query_conditions = {
    "Inpatient Record": "inpatient_patch.inpatient_patch.handover_board.ip_permission_query",
}
has_permission = {
    "Inpatient Record": "inpatient_patch.inpatient_patch.handover_board.ip_has_permission",
}


def _stage(dt):
    return {dt: {"after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage",
                 "on_submit": "inpatient_patch.inpatient_patch.workflow.update_stage"}}


doc_events = {
    "Inpatient Record": {
        "validate": "inpatient_patch.inpatient_patch.billing.guard_inpatient_discharge",
        "after_insert": "inpatient_patch.inpatient_patch.department.apply_admission_protocol",
        "on_update": "inpatient_patch.inpatient_patch.billing.refresh_inpatient_billing_summary",
    },
    "Clinical Procedure": {
        "validate": "inpatient_patch.inpatient_patch.ot.validate_clinical_procedure",
        "on_update": "inpatient_patch.inpatient_patch.ot.on_update_clinical_procedure",
    },
    "Inpatient Service Order": {
        "on_submit": "inpatient_patch.inpatient_patch.billing.on_submit_service_order",
        "on_cancel": "inpatient_patch.inpatient_patch.billing.on_cancel_service_order",
    },
    "Patient Deposit": {
        "on_submit": "inpatient_patch.inpatient_patch.billing.on_submit_deposit",
        "on_cancel": "inpatient_patch.inpatient_patch.billing.on_cancel_deposit",
    },
    "Sales Invoice": {
        "on_submit": "inpatient_patch.inpatient_patch.billing.on_submit_sales_invoice",
        "on_cancel": "inpatient_patch.inpatient_patch.billing.on_cancel_sales_invoice",
        "before_cancel": "inpatient_patch.inpatient_patch.billing.before_cancel_sales_invoice",
    },
    "Payment Entry": {
        "on_submit": "inpatient_patch.inpatient_patch.billing.on_submit_payment_entry",
        "on_cancel": "inpatient_patch.inpatient_patch.billing.on_cancel_payment_entry",
    },
    "Operation Procedure Note": {
        "validate": "inpatient_patch.inpatient_patch.ot.validate_procedure_note",
        "after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage",
        "on_submit": "inpatient_patch.inpatient_patch.workflow.update_stage",
    },
    "Pre Operative Checklist": {
        "validate": "inpatient_patch.inpatient_patch.ot.validate_preop_checklist",
        "on_update": "inpatient_patch.inpatient_patch.workflow.update_stage",
    },
    "Surgical Safety Checklist": {
        "validate": "inpatient_patch.inpatient_patch.ot.validate_safety_checklist",
    },
    "Discharge Summary": {
        "before_submit": "inpatient_patch.inpatient_patch.workflow.before_submit_discharge",
        "on_submit": [
            "inpatient_patch.inpatient_patch.workflow.update_stage",
            "inpatient_patch.inpatient_patch.workflow.create_discharge_followup",
            "inpatient_patch.inpatient_patch.nurse_handover.close_on_discharge",
        ],
    },
    # stage tracking + patient notification for the remaining sheets
    "Emergency Assessment Sheet": {
        "after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage",
        "on_submit": "inpatient_patch.inpatient_patch.billing.auto_bill_emergency",
        "on_cancel": "inpatient_patch.inpatient_patch.billing.cancel_sheet_invoices"},
    "Nursing Admission Assessment": {
        "validate": "inpatient_patch.inpatient_patch.workflow.stamp_nursing_complete",
        "after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage"},
    "Medication Administration Record": {
        "validate": "inpatient_patch.inpatient_patch.workflow.stamp_nursing_complete",
        "on_update": "inpatient_patch.inpatient_patch.handover_board.create_vitals_from_mar"},
    "History Clinical Examination": {
        "after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage"},
    "Recovery Nurse Record": {
        "after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage"},
    "Nurse Handover": {
        "before_save": "inpatient_patch.inpatient_patch.nurse_handover.stamp_updated"},
    "Nurse Admission Assignment": {
        "on_update": "inpatient_patch.inpatient_patch.handover_board.push_assignments_to_records"},
    "Daily Round Plan": {
        "on_submit": "inpatient_patch.inpatient_patch.billing.bill_sheet_prescriptions",
        "on_cancel": "inpatient_patch.inpatient_patch.billing.cancel_sheet_invoices"},
}

# ---- scheduled jobs -------------------------------------------------------
# Runs hourly; the controller only acts at the configured hour (default 12:00).
scheduler_events = {
    "cron": {
        "0 * * * *": [
            "inpatient_patch.inpatient_patch.billing.run_daily_bed_billing",
        ],
    },
}

# ---- install / migrate / uninstall ---------------------------------------
after_install = [
    "inpatient_patch.inpatient_patch.patches.create_custom_fields.execute",
    "inpatient_patch.inpatient_patch.patches.create_custom_fields.force_sync_doctypes",
    "inpatient_patch.inpatient_patch.install.after_install",
]
after_migrate = [
    "inpatient_patch.inpatient_patch.patches.create_custom_fields.force_sync_doctypes",
    "inpatient_patch.inpatient_patch.patches.create_custom_fields.execute",
]
before_uninstall = "inpatient_patch.inpatient_patch.uninstall.before_uninstall"

# ---- fixtures (ship the workspace & reports) ------------------------------
fixtures = [
    {"doctype": "Workspace", "filters": [["name", "in", ["Inpatient Suite"]]]},
]
