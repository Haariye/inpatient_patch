// Emergency admission path: when the ER decision is "Admitted", offer a button
// to start a native Inpatient Record (keeping the standard healthcare admission
// flow). The new record is pre-filled with the patient + department.
frappe.ui.form.on('Emergency Assessment Sheet', {
    refresh(frm) {
        warn_if_admitted(frm);
        if (frm.is_new() === false && frm.doc.patient) {
            frm.add_custom_button(__('Fetch Findings'), () => {
                frappe.call({
                    method: 'inpatient_patch.inpatient_patch.billing.fetch_lab_findings',
                    args: { patient: frm.doc.patient, inpatient_record: frm.doc.inpatient_record },
                    freeze: true, freeze_message: __('Fetching lab results...'),
                    callback(r) {
                        const rows = r.message || [];
                        if (!rows.length) { frappe.msgprint(__('No lab results found for this patient.')); return; }
                        frm.clear_table('lab_findings');
                        rows.forEach((row) => {
                            const d = frm.add_child('lab_findings');
                            d.lab_test = row.lab_test; d.test_name = row.test_name;
                            d.status = row.status; d.result_date = row.result_date; d.finding = row.finding;
                        });
                        frm.refresh_field('lab_findings');
                        frappe.show_alert({ message: __('{0} findings fetched', [rows.length]), indicator: 'green' });
                    },
                });
            });
        }
        if (frm.is_new()) return;
        if (frm.doc.final_decision === 'Admitted' && !frm.doc.inpatient_record) {
            frm.add_custom_button(__('Admit Patient'), () => {
                frappe.call({
                    method: 'inpatient_patch.inpatient_patch.billing.admit_from_emergency',
                    args: { emergency: frm.doc.name }, freeze: true,
                    freeze_message: __('Creating the Inpatient Record...'),
                    callback(r) {
                        if (r.message) {
                            frm.reload_doc();
                            frappe.msgprint({
                                title: __('Inpatient Record created'),
                                indicator: 'green',
                                message: __('Inpatient Record <b>{0}</b> was created. Now <b>Submit</b> this Emergency Assessment Sheet to bill the prescribed items.', [r.message]),
                            });
                        }
                    },
                });
            }).addClass('btn-primary');
        }
        if (frm.doc.inpatient_record) {
            frm.add_custom_button(__('Open Inpatient Record'), () =>
                frappe.set_route('Form', 'Inpatient Record', frm.doc.inpatient_record),
                __('View'));
        }
    },
    patient(frm) {
        warn_if_admitted(frm);
    },
});

function warn_if_admitted(frm) {
    try { frm.dashboard.clear_headline(); } catch (e) {}
    if (!frm.doc.patient || frm.doc.inpatient_record) return;
    frappe.db.get_list('Inpatient Record', {
        filters: { patient: frm.doc.patient, status: ['in', ['Admitted', 'Admission Scheduled']] },
        fields: ['name', 'status'], limit: 1,
    }).then((rows) => {
        if (rows && rows.length) {
            const r = rows[0];
            frm.dashboard.set_headline(
                __('\u26D4 This patient is already {0} (Inpatient Record {1}). Do not admit again.', [r.status, r.name]),
                'red');
            frappe.msgprint({
                title: __('Already Admitted'), indicator: 'red',
                message: __('This patient is already {0} (Inpatient Record {1}). Do not admit again.', [r.status, r.name]),
            });
        }
    });
}
