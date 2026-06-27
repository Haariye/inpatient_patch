// Inpatient Record hub: a guided control panel.
// Buttons appear ONLY when the previous step is done (stage-gated), so the user
// is walked through the workflow. A banner shows the recommended next step.

frappe.ui.form.on('Inpatient Record', {
    refresh(frm) {
        if (frm.is_new()) return;
        frappe.call({
            method: 'inpatient_patch.inpatient_patch.workflow.get_stage',
            args: { inpatient_record: frm.doc.name },
            callback(r) {
                const stage = r.message || {};
                build_buttons(frm, stage);
                show_next_step(frm, stage);
                render_snapshot(frm);
            },
        });
        add_billing_buttons(frm);
        add_view_buttons(frm);
    },
});

function add(frm, label, sheet, group) {
    frm.add_custom_button(__(label), () => create_sheet(frm, sheet), __(group));
}

function build_buttons(frm, s) {
    // ---- Admission (always) ----
    add(frm, 'Emergency Assessment Sheet', 'Emergency Assessment Sheet', 'Admission');
    add(frm, 'Admission Social Data', 'Admission Social Data', 'Admission');
    add(frm, 'Nursing Admission Assessment', 'Nursing Admission Assessment', 'Admission');
    add(frm, 'History & Clinical Examination', 'History Clinical Examination', 'Admission');

    // ---- Ward (after nursing assessment) ----
    if (s.has_nursing) {
        add(frm, 'Progress Note', 'Progress Note', 'Ward');
        add(frm, 'Daily Round Plan', 'Daily Round Plan', 'Ward');
        add(frm, 'Doctor Order', 'Doctor Order', 'Ward');
        add(frm, 'Medication Administration Record', 'Medication Administration Record', 'Ward');
        add(frm, 'Diabetic Insulin Chart', 'Diabetic Insulin Chart', 'Ward');
        add(frm, 'Nurse Handover', 'Nurse Handover', 'Ward');
    }

    // ---- Operation (surgical departments only) ----
    if (s.is_surgical) {
        if (s.has_history) {
            add(frm, 'Cardiac Review', 'Pre Operation Cardiac Review', 'Operation (OT)');
            add(frm, 'Pre-Anesthetic Assessment', 'Pre Anesthetic Assessment', 'Operation (OT)');
            add(frm, 'Surgical Consent Form', 'Surgical Consent Form', 'Operation (OT)');
            add(frm, 'Pre-Operative Checklist', 'Pre Operative Checklist', 'Operation (OT)');
        }
        if (s.preop_ready) {
            add(frm, 'Operation Theatre Case', 'Operation Theatre Case', 'Operation (OT)');
            add(frm, 'Surgical Safety Checklist', 'Surgical Safety Checklist', 'Operation (OT)');
            add(frm, 'OR Tracking Board', 'OR Tracking Board', 'Operation (OT)');
            add(frm, 'Operation / Procedure Note', 'Operation Procedure Note', 'Operation (OT)');
        }
        if (s.operated) {
            add(frm, 'Recovery Nurse Record', 'Recovery Nurse Record', 'Operation (OT)');
            add(frm, 'Post Operative Checklist', 'Post Operative Checklist', 'Operation (OT)');
        }
    }

    // ---- Discharge (after recovery for surgical, after exam otherwise) ----
    const can_discharge = s.is_surgical ? s.has_recovery : s.has_history;
    if (can_discharge) {
        add(frm, 'Discharge Summary', 'Discharge Summary', 'Discharge');
    }
}

function show_next_step(frm, s) {
    let next = null;
    if (!s.has_emergency && !s.has_admission_data) next = 'Record the Emergency Assessment or Admission Social Data.';
    else if (!s.has_nursing) next = 'Complete the Nursing Admission Assessment.';
    else if (!s.has_history) next = 'Complete the History & Clinical Examination.';
    else if (s.is_surgical && !s.preop_ready) next = 'Prepare the patient: finish the Pre-Operative Checklist (tick READY FOR OR).';
    else if (s.is_surgical && !s.operated) next = 'Run the Operation Theatre Case, then the Procedure Note.';
    else if (s.is_surgical && !s.has_recovery) next = 'Record the Recovery Nurse Record.';
    else if (!s.discharged) next = 'When ready, complete the Discharge Summary.';
    else next = 'Admission complete \u2014 patient discharged.';

    frm.dashboard.clear_headline();
    frm.dashboard.set_headline(
        `<span style="font-weight:600;">Next step:</span> ${frappe.utils.escape_html(next)}`);
}

function create_sheet(frm, sheet) {
    frappe.route_options = { inpatient_record: frm.doc.name, patient: frm.doc.patient };
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

function add_view_buttons(frm) {
    frm.add_custom_button(__('Care Timeline'), () => {
        frappe.set_route('List', 'Patient Notification', { inpatient_record: frm.doc.name });
    }, __('View'));
    frm.add_custom_button(__('Nurse Handovers'), () => {
        frappe.set_route('List', 'Nurse Handover', { inpatient_record: frm.doc.name });
    }, __('View'));
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
            frm.dashboard.add_section(html, __('Clinical Sheets'));
        },
    });
}
