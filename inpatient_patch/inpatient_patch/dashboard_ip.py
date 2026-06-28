# Copyright (c) 2026, Dagaar
import frappe


def get_dashboard_data(data=None):
    return {
        "fieldname": "inpatient_record",
        "non_standard_fieldnames": {
            "Sales Invoice": "custom_inpatient_record",
            "Patient Encounter": "custom_inpatient_record",
        },
        "transactions": [
            {"label": "Admission & Nursing", "items": [
                "Emergency Assessment Sheet", "Admission Social Data",
                "Nursing Admission Assessment", "History Clinical Examination",
                "Progress Note", "Daily Round Plan", "Doctor Order",
                "Medication Administration Record", "Diabetic Insulin Chart",
                "Nurse Handover"]},
            {"label": "Operation", "items": [
                "Pre Operation Cardiac Review", "Pre Anesthetic Assessment",
                "Surgical Consent Form", "Pre Operative Checklist",
                "Operation Theatre Case", "Surgical Safety Checklist",
                "OR Tracking Board", "Operation Procedure Note",
                "Recovery Nurse Record", "Post Operative Checklist"]},
            {"label": "Billing", "items": [
                "Inpatient Service Order", "Patient Deposit", "Sales Invoice"]},
            {"label": "Discharge & Care Log", "items": [
                "Discharge Summary", "Patient Notification"]},
            {"label": "Source", "items": ["Patient Encounter"]},
        ],
    }
