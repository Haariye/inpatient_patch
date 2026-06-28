// Nurse Handover: pull today's given medicines, and acknowledge on receipt.
frappe.ui.form.on('Nurse Handover', {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.inpatient_record && frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Pull Today\u2019s MAR'), () => {
                frappe.call({
                    method: 'inpatient_patch.inpatient_patch.workflow.get_shift_medications',
                    args: { inpatient_record: frm.doc.inpatient_record }, freeze: true,
                    callback(r) {
                        const rows = r.message || [];
                        if (!rows.length) { frappe.msgprint(__('No administered medicines found today.')); return; }
                        frm.clear_table('meds_given');
                        rows.forEach((row) => {
                            const d = frm.add_child('meds_given');
                            d.given_at = row.given_at; d.drug_code = row.drug_code;
                            d.dose = row.dose; d.status = row.status; d.given_by = row.given_by;
                        });
                        frm.refresh_field('meds_given');
                        frappe.show_alert({ message: __('{0} medicines pulled', [rows.length]), indicator: 'green' });
                    },
                });
            });
        }
        if (frm.doc.docstatus === 1 && !frm.doc.acknowledged) {
            frm.add_custom_button(__('Acknowledge Handover'), () => {
                frm.set_value('acknowledged', 1);
                frm.set_value('acknowledged_at', frappe.datetime.now_datetime());
                frm.save_or_update();
            }).addClass('btn-primary');
        }
    },
});
