# Copyright (c) 2026, Dagaar
import frappe


def execute(filters=None):
    columns = [
        {"label": "Patient", "fieldname": "patient_name", "fieldtype": "Data", "width": 170},
        {"label": "Inpatient Record", "fieldname": "inpatient_record", "fieldtype": "Link",
         "options": "Inpatient Record", "width": 160},
        {"label": "Invoice", "fieldname": "invoice", "fieldtype": "Link",
         "options": "Sales Invoice", "width": 150},
        {"label": "Type", "fieldname": "type", "fieldtype": "Data", "width": 120},
        {"label": "Status", "fieldname": "docstatus", "fieldtype": "Data", "width": 90},
        {"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Currency", "width": 120},
        {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 120},
    ]
    rows = frappe.db.sql("""
        select si.patient_name, si.custom_inpatient_record as inpatient_record,
               si.name as invoice,
               case when si.custom_is_inpatient_bed_invoice=1 then 'Bed'
                    when si.custom_is_consumable_invoice=1 then 'OT Consumable'
                    when si.custom_is_inpatient_service_invoice=1 then 'Service'
                    else 'Other' end as type,
               case si.docstatus when 0 then 'Draft' when 1 then 'Submitted' else 'Cancelled' end as docstatus,
               si.grand_total, si.outstanding_amount
        from `tabSales Invoice` si
        where si.custom_inpatient_record is not null
          and si.docstatus < 2
          and (si.outstanding_amount > 0 or si.docstatus = 0)
        order by si.posting_date desc
    """, as_dict=True)
    return columns, rows
