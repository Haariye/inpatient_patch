// Inpatient Record hub: turns the existing Inpatient Record into a one-stop
// control panel. Buttons (grouped) create each clinical sheet pre-linked to the
// record; a snapshot panel shows what already exists; quick billing actions.

frappe.ui.form.on('Inpatient Record', {
    refresh(frm) {
        if (frm.is_new()) return;
        add_workflow_buttons(frm);
        add_billing_buttons(frm);
        render_snapshot(frm);
    },
});

const GROUPS = {
    'Admission': [
        'Emergency Assessment Sheet', 'Admission Social Data',
        'Nursing Admission Assessment', 'History Clinical Examination',
    ],
    'Ward': [
        'Progress Note', 'Daily Round Plan', 'Doctor Order',
        'Medication Administration Record', 'Diabetic Insulin Chart',
    ],
    'Operation (OT)': [
        'Operation Theatre Case', 'Pre Operation Cardiac Review',
        'Pre Anesthetic Assessment', 'Pre Operative Checklist',
        'Surgical Consent Form', 'Surgical Safety Checklist',
        'OR Tracking Board', 'Operation Procedure Note',
        'Post Operative Checklist', 'Recovery Nurse Record',
    ],
    'Discharge': ['Discharge Summary'],
};

function add_workflow_buttons(frm) {
    Object.keys(GROUPS).forEach((group) => {
        GROUPS[group].forEach((sheet) => {
            frm.add_custom_button(__(sheet), () => create_sheet(frm, sheet), __(group));
        });
    });
}

function create_sheet(frm, sheet) {
    // Open a fresh, pre-linked form so the user can fill mandatory fields,
    // then Save. inpatient_record is pre-set; patient auto-fetches from it.
    frappe.route_options = {
        inpatient_record: frm.doc.name,
        patient: frm.doc.patient,
    };
    frappe.new_doc(sheet);
}

function add_billing_buttons(frm) {
    frm.add_custom_button(__('Deposit'), () => open_deposit_dialog(frm), __('Billing'));
    frm.add_custom_button(__('Send Service to Billing'),
        () => create_sheet(frm, 'Inpatient Service Order'), __('Billing'));
    frm.add_custom_button(__('Bill Bed Now'), () => {
        frappe.call({
            method: 'inpatient_patch.inpatient_patch.billing.bill_bed_for_record',
            args: { inpatient_record: frm.doc.name },
            freeze: true,
            callback(r) {
                if (r.message) {
                    frappe.show_alert({ message: __('Draft bed invoice {0} created', [r.message]), indicator: 'green' });
                    frm.reload_doc();
                }
            },
        });
    }, __('Billing'));
}

function open_deposit_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __('Add Deposit'),
        fields: [
            { fieldname: 'amount', label: __('Amount (USD)'), fieldtype: 'Currency', reqd: 1 },
            { fieldname: 'mode_of_payment', label: __('Mode of Payment'), fieldtype: 'Link', options: 'Mode of Payment' },
            { fieldname: 'remarks', label: __('Remarks'), fieldtype: 'Small Text' },
        ],
        primary_action_label: __('Save Deposit'),
        primary_action(values) {
            frappe.db.insert({
                doctype: 'Patient Deposit',
                inpatient_record: frm.doc.name,
                patient: frm.doc.patient,
                deposit_date: frappe.datetime.now_datetime(),
                amount: values.amount,
                mode_of_payment: values.mode_of_payment,
                remarks: values.remarks,
            }).then((doc) => {
                frappe.call({ method: 'frappe.client.submit', args: { doc } }).then(() => {
                    d.hide();
                    frappe.show_alert({ message: __('Deposit recorded'), indicator: 'green' });
                    frm.reload_doc();
                });
            });
        },
    });
    d.show();
}

function render_snapshot(frm) {
    frappe.call({
        method: 'inpatient_patch.inpatient_patch.hub.get_snapshot',
        args: { inpatient_record: frm.doc.name },
        callback(r) {
            if (!r.message) return;
            const counts = r.message;
            let html = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin:8px 0;">';
            Object.keys(counts).forEach((sheet) => {
                const n = counts[sheet];
                const color = n ? '#1f9d55' : '#adb5bd';
                html += `<span style="border:1px solid ${color};color:${color};
                    border-radius:12px;padding:2px 10px;font-size:12px;">
                    ${frappe.utils.escape_html(sheet)} : <b>${n}</b></span>`;
            });
            html += '</div>';
            if (!frm.fields_dict.__snapshot) {
                frm.dashboard.add_section(html, __('Clinical Sheets'));
            }
        },
    });
}
