// Inpatient Record hub: a simple, guided control panel.
// - One "Next step" banner tells staff what to do now.
// - Three tidy menus: "Care Steps", "Billing", "View".
// - A step's button disappears once that step is done; the next one appears.
// - The "Clinical Sheets" badges are live links to the filtered lists.

frappe.ui.form.on('Inpatient Record', {
    refresh(frm) {
        if (frm.is_new()) return;
        frm_clear_dynamic(frm);
        frappe.call({
            method: 'inpatient_patch.inpatient_patch.workflow.get_stage',
            args: { inpatient_record: frm.doc.name },
            callback(r) {
                const s = r.message || {};
                build_care_menu(frm, s);
                add_billing_menu(frm);
                add_view_menu(frm, s);
                show_next_step(frm, s);
                render_snapshot(frm, s);
            },
        });
    },
});

function frm_clear_dynamic(frm) {
    // custom buttons are rebuilt on every refresh by Frappe, nothing to clear.
}

function go(frm, sheet) {
    frappe.route_options = { inpatient_record: frm.doc.name, patient: frm.doc.patient };
    frappe.new_doc(sheet);
}

const CARE = 'Care Steps';

function build_care_menu(frm, s) {
    // ----- Admission phase -----
    if (!s.has_admission_data) frm.add_custom_button(__('Admission Social Data'), () => go(frm, 'Admission Social Data'), __(CARE));
    if (!s.has_nursing)        frm.add_custom_button(__('Nursing Admission Assessment'), () => go(frm, 'Nursing Admission Assessment'), __(CARE));
    if (s.has_nursing && !s.has_history) frm.add_custom_button(__('History & Clinical Examination'), () => go(frm, 'History Clinical Examination'), __(CARE));

    // ----- Ward phase (after nursing assessment) : repeatable tools -----
    if (s.has_nursing) {
        frm.add_custom_button(__('Progress Note'), () => go(frm, 'Progress Note'), __(CARE));
        frm.add_custom_button(__('Doctor Order'), () => go(frm, 'Doctor Order'), __(CARE));
        frm.add_custom_button(__('Medication Administration (MAR)'), () => go(frm, 'Medication Administration Record'), __(CARE));
        frm.add_custom_button(__('Diabetic Insulin Chart'), () => go(frm, 'Diabetic Insulin Chart'), __(CARE));
        frm.add_custom_button(__('Daily Round Plan'), () => go(frm, 'Daily Round Plan'), __(CARE));
        frm.add_custom_button(__('Nurse Handover'), () => go(frm, 'Nurse Handover'), __(CARE));
    }

    // ----- Operation phase (surgical only) -----
    if (s.is_surgical) {
        if (s.has_history && !s.preop_ready) {
            frm.add_custom_button(__('Cardiac Review'), () => go(frm, 'Pre Operation Cardiac Review'), __(CARE));
            frm.add_custom_button(__('Pre-Anesthetic Assessment'), () => go(frm, 'Pre Anesthetic Assessment'), __(CARE));
            if (!s.has_consent) frm.add_custom_button(__('Surgical Consent Form'), () => go(frm, 'Surgical Consent Form'), __(CARE));
            frm.add_custom_button(__('Pre-Operative Checklist'), () => go(frm, 'Pre Operative Checklist'), __(CARE));
        }
        if (s.preop_ready && !s.operated) {
            frm.add_custom_button(__('Operation Theatre Case'), () => go(frm, 'Operation Theatre Case'), __(CARE));
            frm.add_custom_button(__('Surgical Safety Checklist'), () => go(frm, 'Surgical Safety Checklist'), __(CARE));
            frm.add_custom_button(__('OR Tracking Board'), () => go(frm, 'OR Tracking Board'), __(CARE));
            frm.add_custom_button(__('Operation / Procedure Note'), () => go(frm, 'Operation Procedure Note'), __(CARE));
        }
        if (s.operated) {
            if (!s.has_recovery) frm.add_custom_button(__('Recovery Nurse Record'), () => go(frm, 'Recovery Nurse Record'), __(CARE));
            if (!s.has_postop)   frm.add_custom_button(__('Post-Operative Checklist'), () => go(frm, 'Post Operative Checklist'), __(CARE));
        }
    }

    // ----- Discharge -----
    const can_discharge = s.is_surgical ? s.has_recovery : s.has_history;
    if (can_discharge && !s.discharged) {
        frm.add_custom_button(__('Discharge Summary'), () => go(frm, 'Discharge Summary'), __(CARE));
    }
}

function add_billing_menu(frm) {
    frm.add_custom_button(__('Deposit'), () => open_deposit_dialog(frm), __('Billing'));
    frm.add_custom_button(__('Send Service to Billing'), () => go(frm, 'Inpatient Service Order'), __('Billing'));
    frm.add_custom_button(__('Bill Bed Now'), () => {
        frappe.call({
            method: 'inpatient_patch.inpatient_patch.billing.bill_bed_for_record',
            args: { inpatient_record: frm.doc.name }, freeze: true,
            callback(r) { if (r.message) { frappe.show_alert({ message: __('Draft bed invoice {0} created', [r.message]), indicator: 'green' }); frm.reload_doc(); } },
        });
    }, __('Billing'));
}

function add_view_menu(frm, s) {
    const L = (dt) => frappe.set_route('List', dt, { inpatient_record: frm.doc.name });
    frm.add_custom_button(__('Care Timeline (notifications)'), () => L('Patient Notification'), __('View'));
    frm.add_custom_button(__('Nurse Handovers'), () => L('Nurse Handover'), __('View'));
    frm.add_custom_button(__('Invoices'), () => frappe.set_route('List', 'Sales Invoice', { custom_inpatient_record: frm.doc.name }), __('View'));
}

function show_next_step(frm, s) {
    let next;
    if (!s.has_nursing) next = 'Complete the Nursing Admission Assessment (Care Steps menu).';
    else if (!s.has_history) next = 'Complete the History & Clinical Examination.';
    else if (s.is_surgical && !s.preop_ready) next = 'Prepare for theatre: finish the Pre-Operative Checklist and tick READY FOR OR.';
    else if (s.is_surgical && !s.operated) next = 'Run the Operation Theatre Case, then the Procedure Note.';
    else if (s.is_surgical && !s.has_recovery) next = 'Record the Recovery Nurse Record.';
    else if (!s.discharged) next = 'When ready, complete the Discharge Summary.';
    else next = 'Admission complete \u2014 patient discharged.';
    frm.dashboard.clear_headline();
    frm.dashboard.set_headline('<span style="font-weight:600;">Next step:</span> ' + frappe.utils.escape_html(next));
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
                doctype: 'Patient Deposit', inpatient_record: frm.doc.name, patient: frm.doc.patient,
                deposit_date: frappe.datetime.now_datetime(), amount: values.amount,
                mode_of_payment: values.mode_of_payment, remarks: values.remarks,
            }).then((doc) => {
                frappe.call({ method: 'frappe.client.submit', args: { doc } }).then(() => {
                    d.hide(); frappe.show_alert({ message: __('Deposit recorded'), indicator: 'green' }); frm.reload_doc();
                });
            });
        },
    });
    d.show();
}

function render_snapshot(frm, stage) {
    frappe.call({
        method: 'inpatient_patch.inpatient_patch.hub.get_snapshot',
        args: { inpatient_record: frm.doc.name },
        callback(r) {
            if (!r.message) return;
            const counts = r.message;
            let html = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin:8px 0;">';
            Object.keys(counts).forEach((sheet) => {
                const n = counts[sheet];
                const color = n ? '#1f9d55' : '#9aa0a6';
                const slug = frappe.router.slug(sheet);
                const url = '/app/' + slug + '?inpatient_record=' + encodeURIComponent(frm.doc.name);
                html += '<a href="' + url + '" style="text-decoration:none;border:1px solid ' + color +
                    ';color:' + color + ';border-radius:12px;padding:2px 10px;font-size:12px;">' +
                    frappe.utils.escape_html(sheet) + ' : <b>' + n + '</b></a>';
            });
            html += '</div>';
            frm.dashboard.add_section(html, __('Clinical Sheets (click to open)'));
        },
    });
}
