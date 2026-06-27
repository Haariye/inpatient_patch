# Installing Inpatient Patch

> Built against **Frappe / ERPNext Healthcare v15**. It is a *separate app*
> that only **adds** custom fields + new doctypes, so install/uninstall is safe.

## 0. Prerequisites
* A working bench with `frappe` **v15** and the **healthcare** app installed.
* A Company, a Customer linked to each Patient (standard healthcare setup),
  and item/stock setup if you will issue OT consumables.

## 1. Get & install the app
```bash
cd /path/to/your-bench
bench get-app inpatient_patch /path/to/inpatient_patch     # or your git URL
bench --site yoursite install-app inpatient_patch
bench --site yoursite migrate
bench build
bench --site yoursite clear-cache
```
`after_install` will:
* create all custom fields on existing doctypes (idempotent),
* seed **Inpatient Billing Settings** (USD, daily run hour = 12),
* seed example **Department Admission Protocols** (Orthopedic, Pediatrics,
  Obstetrics & Gynecology, Internal Medicine) - edit or add your own.

## 2. One-time configuration
1. **Inpatient Billing Settings** - set Default Company, Bed Income Account,
   Deposit Account / Mode of Payment. Confirm `Daily Run Hour = 12`.
2. **Healthcare Service Unit Type** (for each bed type) - set
   *Daily Bed Rate (USD)* and *Bed Charge Item* (the new custom fields). The
   daily job needs these to raise the bed invoice.
3. **Department Admission Protocol** - review the seeded protocols; add a row
   per medical department you use, listing the required forms + default orders.
4. Make sure each **Patient** has a linked **Customer** (billing needs it).

## 3. Daily usage
* Open an **Inpatient Record**. Set *Medical Department* and *Current Bed*.
  On creation the matching protocol is stamped and a guidance comment lists the
  department's required forms.
* Use the grouped buttons (**Admission / Ward / Operation (OT) / Discharge** and
  **Billing**) to open each clinical sheet, already linked to the record.
* Checkboxes reveal their dependent ("children") fields when ticked.
* **Nurse station**: in the *Medication Administration Record*, tick **Given**
  to reveal *Time Given* + *Nurse (Given By)* - capturing exactly when each dose
  was given and by whom.
* **Operation Theatre Case**: fill consumables/implants and **Submit** - stock
  is issued (Material Issue) and a draft consumable invoice is raised.
* **Billing**:
  * The **bed** is billed automatically every day at 12:00 (draft invoice).
  * **Send Service to Billing** (pharmacy/lab/radiology) -> draft-but-billable
    Sales Invoice immediately.
  * **Deposit** -> one click records an advance Payment Entry.
* Watch **Inpatient Census**, **Inpatient Outstanding Bills** and
  **Medication Due List** reports + the *Inpatient Suite* workspace.

## 4. Safety checklist before going live
- [ ] Test on a **staging site** first.
- [ ] Confirm bed rate + bed item are set on each Service Unit Type.
- [ ] Confirm each Patient has a Customer.
- [ ] Verify the scheduler is running (`bench doctor` / `bench enable-scheduler`).
- [ ] Do a full dry-run: admit -> sheets -> OT -> deposit -> bed invoice ->
      service invoice -> discharge.

## 5. Clean uninstall (reverts your app to its prior state)
```bash
bench --site yoursite uninstall-app inpatient_patch
bench --site yoursite migrate
bench build && bench --site yoursite clear-cache
```
`before_uninstall` removes every custom field this app added; bench removes the
app's own doctypes and their data. Your original healthcare app is untouched.

> **Note on your fork:** this app targets the *standard* Healthcare v15 field
> names (your private repo was not reachable during the build). Because it only
> **adds** fields, it will not break a fork - but if your fork renamed core
> fields (e.g. `Inpatient Record.patient`), adjust the `fetch_from`/filters
> accordingly. Search the app for `fetch_from` to review.
