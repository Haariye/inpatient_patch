// MAR: pull what the doctor prescribed so the nurse administers exactly that.
frappe.ui.form.on('Medication Administration Record', {
    onload(frm) {
        if (frm.is_new()) {
            frappe.call({ method: 'inpatient_patch.inpatient_patch.handover_board.session_nurse_and_shift',
                callback(r) {
                    const m = r.message || {};
                    if (m.nurse && !frm.doc.recording_nurse) frm.set_value('recording_nurse', m.nurse);
                    if (m.shift && !frm.doc.shift) frm.set_value('shift', m.shift);
                } });
        }
    },
    refresh(frm) {
        if (!frm.is_new() && frm.doc.inpatient_record) {
            frm.add_custom_button(__('Pull Prescribed Medicines'), () => {
                frappe.call({
                    method: 'inpatient_patch.inpatient_patch.billing.pull_prescribed_medicines',
                    args: { inpatient_record: frm.doc.inpatient_record }, freeze: true,
                    callback(r) {
                        const rows = r.message || [];
                        if (!rows.length) { frappe.msgprint(__('No prescribed medicines found on the encounter.')); return; }
                        rows.forEach((row) => {
                            const c = frm.add_child('entries');
                            c.drug_code = row.drug_code; c.drug_name = row.drug_name;
                            c.dose = row.dose; c.status = 'Pending';
                        });
                        frm.refresh_field('entries');
                        frappe.show_alert({ message: __('{0} prescribed medicines added', [rows.length]), indicator: 'green' });
                    },
                });
            }).addClass('btn-primary');
        }
    },
});
