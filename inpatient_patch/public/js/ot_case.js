frappe.ui.form.on('Operation Theatre Case', {
    onload(frm) {
        frm.set_query('theatre', () => ({
            query: 'inpatient_patch.inpatient_patch.ot.ot_facility_query',
        }));
    },
    refresh(frm) {
        if (!frm.is_new() && frm.doc.docstatus === 0) {
            if (!frm.doc.surgery_start_time) {
                frm.add_custom_button(__('\u25B6 Start Operation'), () => {
                    frappe.call({
                        method: 'inpatient_patch.inpatient_patch.ot.start_operation',
                        args: { ot_case: frm.doc.name }, freeze: true,
                        callback() { frm.reload_doc(); frappe.show_alert({ message: __('Operation started'), indicator: 'green' }); },
                    });
                }).addClass('btn-success');
            } else if (!frm.doc.surgery_end_time) {
                frm.add_custom_button(__('\u23F9 End Operation'), () => {
                    frappe.call({
                        method: 'inpatient_patch.inpatient_patch.ot.end_operation',
                        args: { ot_case: frm.doc.name }, freeze: true,
                        callback() { frm.reload_doc(); frappe.show_alert({ message: __('Operation ended'), indicator: 'blue' }); },
                    });
                }).addClass('btn-danger');
            }
        }
        if (frm.doc.stock_entry) {
            frm.add_custom_button(__('Stock Entry'), () =>
                frappe.set_route('Form', 'Stock Entry', frm.doc.stock_entry), __('View'));
        }
        if (frm.doc.consumable_invoice) {
            frm.add_custom_button(__('Consumable Invoice'), () =>
                frappe.set_route('Form', 'Sales Invoice', frm.doc.consumable_invoice), __('View'));
        }
    },
    inpatient_record(frm) {
        if (!frm.doc.inpatient_record) return;
        frappe.db.get_value('Inpatient Record', frm.doc.inpatient_record,
            'custom_medical_department').then((r) => {
                if (r.message && r.message.custom_medical_department) {
                    frm.set_value('medical_department', r.message.custom_medical_department);
                }
            });
    },
});
