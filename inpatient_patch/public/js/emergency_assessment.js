// Emergency admission path: when the ER decision is "Admitted", offer a button
// to start a native Inpatient Record (keeping the standard healthcare admission
// flow). The new record is pre-filled with the patient + department.
frappe.ui.form.on('Emergency Assessment Sheet', {
    refresh(frm) {
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
                frappe.route_options = {
                    patient: frm.doc.patient,
                    custom_emergency_done: 1,
                };
                frappe.new_doc('Inpatient Record');
                frappe.show_alert(__('Complete the native admission, then link this '
                    + 'Emergency Sheet to the new Inpatient Record.'));
            }).addClass('btn-primary');
        }
        if (frm.doc.inpatient_record) {
            frm.add_custom_button(__('Open Inpatient Record'), () =>
                frappe.set_route('Form', 'Inpatient Record', frm.doc.inpatient_record),
                __('View'));
        }
    },
});
