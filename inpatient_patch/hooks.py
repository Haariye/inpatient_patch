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
    "Operation Theatre Case": "public/js/ot_case.js",
    "Emergency Assessment Sheet": "public/js/emergency_assessment.js",
    "Nurse Handover": "public/js/nurse_handover.js",
    "Medication Administration Record": "public/js/mar.js",
}

# ---- document events ------------------------------------------------------
override_doctype_dashboards = {
    "Inpatient Record": "inpatient_patch.inpatient_patch.dashboard_ip.get_dashboard_data",
}


def _stage(dt):
    return {dt: {"after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage",
                 "on_submit": "inpatient_patch.inpatient_patch.workflow.update_stage"}}


doc_events = {
    "Inpatient Record": {
        "after_insert": "inpatient_patch.inpatient_patch.department.apply_admission_protocol",
        "on_update": "inpatient_patch.inpatient_patch.billing.refresh_inpatient_billing_summary",
    },
    "Operation Theatre Case": {
        "validate": "inpatient_patch.inpatient_patch.ot.validate_ot_case",
        "before_submit": "inpatient_patch.inpatient_patch.workflow.before_submit_ot_case",
        "on_submit": "inpatient_patch.inpatient_patch.ot.on_submit_ot_case",
        "on_cancel": "inpatient_patch.inpatient_patch.ot.on_cancel_ot_case",
    },
    "Inpatient Service Order": {
        "on_cancel": "inpatient_patch.inpatient_patch.billing.on_cancel_service_order",
    },
    "Patient Deposit": {
        "on_submit": "inpatient_patch.inpatient_patch.billing.on_submit_deposit",
        "on_cancel": "inpatient_patch.inpatient_patch.billing.on_cancel_deposit",
    },
    "Sales Invoice": {
        "on_submit": "inpatient_patch.inpatient_patch.billing.on_submit_sales_invoice",
        "on_cancel": "inpatient_patch.inpatient_patch.billing.on_cancel_sales_invoice",
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
        ],
    },
    # stage tracking + patient notification for the remaining sheets
    "Emergency Assessment Sheet": {
        "after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage"},
    "Nursing Admission Assessment": {
        "validate": "inpatient_patch.inpatient_patch.workflow.stamp_nursing_complete",
        "after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage"},
    "Medication Administration Record": {
        "validate": "inpatient_patch.inpatient_patch.workflow.stamp_nursing_complete"},
    "History Clinical Examination": {
        "after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage"},
    "Recovery Nurse Record": {
        "after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage"},
    "Nurse Handover": {
        "after_insert": "inpatient_patch.inpatient_patch.workflow.update_stage"},
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
    "inpatient_patch.inpatient_patch.install.after_install",
]
after_migrate = ["inpatient_patch.inpatient_patch.patches.create_custom_fields.execute"]
before_uninstall = "inpatient_patch.inpatient_patch.uninstall.before_uninstall"

# ---- fixtures (ship the workspace & reports) ------------------------------
fixtures = [
    {"doctype": "Workspace", "filters": [["name", "in", ["Inpatient Suite"]]]},
]
