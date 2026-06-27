# Copyright (c) 2026, Dagaar
"""
Clean uninstall: remove every Custom Field this app added to EXISTING doctypes
so the site returns to its pre-install state. The app's own DocTypes (and their
data) are removed automatically by bench uninstall-app.
"""
import frappe
from inpatient_patch.inpatient_patch.patches.create_custom_fields import FIELD_CONFIGS


def before_uninstall():
    for cfg in FIELD_CONFIGS:
        cf = f"{cfg['dt']}-{cfg['fieldname']}"
        if frappe.db.exists("Custom Field", cf):
            try:
                frappe.delete_doc("Custom Field", cf, ignore_permissions=True, force=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"Uninstall remove {cf}")
    frappe.db.commit()
