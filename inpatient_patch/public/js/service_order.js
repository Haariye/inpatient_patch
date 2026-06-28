frappe.ui.form.on('Inpatient Service Order', {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.inpatient_record) {
            frm.add_custom_button(__('Pull from Encounter'), () => {
                frappe.call({
                    method: 'inpatient_patch.inpatient_patch.billing.pull_encounter_orders',
                    args: { inpatient_record: frm.doc.inpatient_record }, freeze: true,
                    callback(r) {
                        const d = r.message || {};
                        ['lab_tests', 'imaging', 'procedures', 'items'].forEach((tbl) => {
                            (d[tbl] || []).forEach((row) => {
                                const c = frm.add_child(tbl);
                                Object.assign(c, row);
                            });
                            frm.refresh_field(tbl);
                        });
                        frappe.show_alert({ message: __('Pulled from encounter'), indicator: 'green' });
                    },
                });
            });
        }
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
