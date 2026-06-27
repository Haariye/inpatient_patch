# Copyright (c) 2026, Dagaar
"""Medicines scheduled but not yet given (nurse-station due list)."""
import frappe


def execute(filters=None):
    columns = [
        {"label": "Patient", "fieldname": "patient_name", "fieldtype": "Data", "width": 160},
        {"label": "MAR", "fieldname": "parent", "fieldtype": "Link",
         "options": "Medication Administration Record", "width": 150},
        {"label": "Drug", "fieldname": "drug_name", "fieldtype": "Data", "width": 150},
        {"label": "Dose", "fieldname": "dose", "fieldtype": "Data", "width": 90},
        {"label": "Route", "fieldname": "route", "fieldtype": "Data", "width": 80},
        {"label": "Scheduled", "fieldname": "scheduled_time", "fieldtype": "Datetime", "width": 160},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 90},
    ]
    rows = frappe.db.sql("""
        select mar.patient_name, e.parent, e.drug_name, e.dose, e.route,
               e.scheduled_time, e.status
        from `tabMedication Administration Entry` e
        join `tabMedication Administration Record` mar on mar.name = e.parent
        where ifnull(e.given,0) = 0 and ifnull(e.status,'Pending') = 'Pending'
        order by e.scheduled_time asc
    """, as_dict=True)
    return columns, rows
