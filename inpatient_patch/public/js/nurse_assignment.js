// Nurse Admission Assignment: load admitted patients, set responsible nurse.
frappe.ui.form.on('Nurse Admission Assignment', {
    onload(frm) {
        if (frm.is_new()) {
            if (!frm.doc.assignment_date) frm.set_value('assignment_date', frappe.datetime.get_today());
            frappe.call({ method: 'inpatient_patch.inpatient_patch.handover_board.session_nurse_and_shift',
                callback(r) { if (r.message && r.message.shift && !frm.doc.shift) frm.set_value('shift', r.message.shift); } });
        }
    },
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__('Load Admitted Patients'), () => {
            frappe.call({ method: 'inpatient_patch.inpatient_patch.handover_board.load_admitted_patients',
                args: { assignment: frm.doc.name }, freeze: true,
                callback() { frm.reload_doc(); } });
        }).addClass('btn-primary');
    },
});
