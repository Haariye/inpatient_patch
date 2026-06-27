frappe.ui.form.on('Inpatient Service Order', {
    refresh(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.status !== 'Billed') {
            frm.add_custom_button(__('Send to Billing'), () => {
                frappe.call({
                    method: 'inpatient_patch.inpatient_patch.billing.send_service_order_to_billing',
                    args: { service_order: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Creating draft invoice...'),
                    callback(r) {
                        if (r.message) {
                            frappe.show_alert({ message: __('Draft invoice {0} created (billable).', [r.message]), indicator: 'green' });
                            frm.reload_doc();
                        }
                    },
                });
            }).addClass('btn-primary');
        }
        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__('Open Invoice'), () => {
                frappe.set_route('Form', 'Sales Invoice', frm.doc.sales_invoice);
            });
        }
    },
});
