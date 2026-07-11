# Copyright (c) 2026, Dagaar
import frappe


def execute(filters=None):
    columns = [
        {"label": "Inpatient Record", "fieldname": "name", "fieldtype": "Link",
         "options": "Inpatient Record", "width": 160},
        {"label": "Patient", "fieldname": "patient_name", "fieldtype": "Data", "width": 160},
        {"label": "Department", "fieldname": "medical_department",
         "fieldtype": "Link", "options": "Medical Department", "width": 140},
        {"label": "Bed", "fieldname": "custom_current_bed", "fieldtype": "Link",
         "options": "Healthcare Service Unit", "width": 130},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": "Billed", "fieldname": "custom_total_billed", "fieldtype": "Currency", "width": 110},
        {"label": "Deposit", "fieldname": "custom_total_deposit", "fieldtype": "Currency", "width": 110},
        {"label": "Outstanding", "fieldname": "custom_outstanding", "fieldtype": "Currency", "width": 120},
    ]
    conditions = {"status": "Admitted"}
    if filters and filters.get("department"):
        conditions["medical_department"] = filters["department"]
    data = frappe.get_all("Inpatient Record", filters=conditions,
        fields=["name", "patient_name", "medical_department",
                "custom_current_bed", "status", "custom_total_billed",
                "custom_total_deposit", "custom_outstanding"])
    return columns, data
