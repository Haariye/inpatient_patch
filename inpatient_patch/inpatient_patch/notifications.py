# Copyright (c) 2026, Dagaar
"""
Patient notifications. Every meaningful step calls notify_patient(), which:
  * writes an auditable Patient Notification log row,
  * raises an in-app Notification Log to the patient's linked User (if any),
  * optionally sends an SMS (if enabled in settings and an SMS sender exists).
It must NEVER raise - notifications are a side effect, not a gate.
"""
import frappe
from frappe import _


def _settings():
    try:
        return frappe.get_single("Inpatient Billing Settings")
    except Exception:
        return None


def notify_patient(inpatient_record, event, message, ref_dt=None, ref_dn=None):
    try:
        patient = frappe.db.get_value("Inpatient Record", inpatient_record, "patient")
        if not patient:
            return
        patient_name, mobile, pat_user = frappe.db.get_value(
            "Patient", patient, ["patient_name", "mobile", "user_id"]) or (None, None, None)

        s = _settings()
        channel = "In-App"
        status = "Logged"

        # 1) audit log row
        log = frappe.get_doc({
            "doctype": "Patient Notification",
            "patient": patient,
            "inpatient_record": inpatient_record,
            "event": event,
            "message": message,
            "channel": channel,
            "status": status,
            "reference_doctype": ref_dt,
            "reference_name": ref_dn,
        })
        log.insert(ignore_permissions=True)

        # 2) in-app notification to the patient's user
        if pat_user and (not s or s.get("send_patient_inapp", 1)):
            try:
                frappe.get_doc({
                    "doctype": "Notification Log",
                    "for_user": pat_user,
                    "type": "Alert",
                    "subject": _("{0}: {1}").format(event, patient_name or patient),
                    "email_content": message,
                    "document_type": ref_dt or "Inpatient Record",
                    "document_name": ref_dn or inpatient_record,
                }).insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "notify in-app")

        # 3) optional SMS
        if s and s.get("send_patient_sms") and mobile:
            try:
                from frappe.core.doctype.sms_settings.sms_settings import send_sms
                send_sms([mobile], message)
                log.db_set("channel", "SMS")
                log.db_set("status", "Sent")
            except Exception:
                log.db_set("status", "Failed")
                frappe.log_error(frappe.get_traceback(), "notify sms")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "notify_patient")
