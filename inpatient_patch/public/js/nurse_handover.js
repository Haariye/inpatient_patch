// Nurse Handover: one-click acknowledge by the receiving nurse.
frappe.ui.form.on('Nurse Handover', {
    refresh(frm) {
        if (frm.doc.docstatus === 1 && !frm.doc.acknowledged) {
            frm.add_custom_button(__('Acknowledge Handover'), () => {
                frm.set_value('acknowledged', 1);
                frm.set_value('acknowledged_at', frappe.datetime.now_datetime());
                frm.save_or_update();
            }).addClass('btn-primary');
        }
    },
});
