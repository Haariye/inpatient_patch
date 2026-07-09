# Copyright (c) 2026, Dagaar
"""
On uninstall we PRESERVE data. We intentionally do NOT delete the custom fields
or any records, so historical inpatient/billing data stays intact (like other
well-behaved apps). To fully remove everything, delete the doctypes manually.
"""
import frappe


def before_uninstall():
    # Keep all data. Nothing is removed.
    frappe.msgprint("Inpatient Patch: data preserved on uninstall.")
