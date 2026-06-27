// Emergency admission path: when the ER decision is "Admitted", offer a button
// to start a native Inpatient Record (keeping the standard healthcare admission
// flow). The new record is pre-filled with the patient + department.
frappe.ui.form.on('Emergency Assessment Sheet', {
    refresh(frm) {
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
