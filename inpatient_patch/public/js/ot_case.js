frappe.ui.form.on('Operation Theatre Case', {
    refresh(frm) {
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
