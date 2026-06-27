# Inpatient Patch

A comprehensive, install-safe **Inpatient + Operating-Theatre + Somali-billing**
extension for ERPNext / Frappe **Healthcare v15**.

It is a *separate app* that depends on `healthcare`. It only **adds** fields and
doctypes; on uninstall it removes everything it added and your app returns to
its previous state.

## What it adds
* The full 20-sheet clinical workflow from the Patient Care Workflow
  Specification (Emergency -> Admission -> Nursing -> History -> Ward ->
  Pre-Op -> OT -> Recovery -> Discharge).
* A nurse-station **Medication Administration Record** capturing the *exact time
  a medicine was given and the nurse who gave it*.
* A high-value **Operation Theatre Case** that, on submit, issues consumables &
  implants (screws) from stock and raises a draft-but-billable pharmacy/
  consumable Sales Invoice.
* **Department Admission Protocols** so an orthopedic / pediatric / maternity /
  etc. admission auto-loads its own forms and default order set.
* **Somali billing**: a daily 12:00 scheduler bills *only the bed*; every other
  service (pharmacy, lab, radiology, OT) becomes a draft-but-billable Sales
  Invoice the moment a nurse/doctor sends it. Plus a one-click **Deposit**.
* Reports, a workspace and a dashboard chart.
* Everything is reachable from the existing **Inpatient Record** via buttons,
  and check-boxes reveal their dependent ("children") fields when ticked.

## Install
```bash
bench get-app inpatient_patch /path/to/inpatient_patch
bench --site yoursite install-app inpatient_patch
bench --site yoursite migrate
bench build && bench clear-cache
```

## Uninstall (clean)
```bash
bench --site yoursite uninstall-app inpatient_patch
```
The `before_uninstall` hook removes all custom fields this app added.

See `INSTALL.md` for the full step-by-step and a safety checklist.
