// Inpatient Record hub: ONE "Create" button opens a grouped menu of the
// actions that are valid right now (gated, and hidden once a step is done).
// A "Next step" banner guides staff; the Clinical Sheets badges are live links.

frappe.ui.form.on('Inpatient Record', {
    refresh(frm) {
        if (frm.is_new()) return;
        // Only before admission do we hide everything and ask to admit.
        if (frm.doc.status === 'Admission Scheduled') {
            frm.dashboard.clear_headline();
            frm.dashboard.set_headline(
                '<span style="font-weight:600;color:#b45309;">Patient not yet admitted.</span> '
                + 'Use the native <b>Admit</b> button (or admit from the Emergency Assessment). '
                + 'Care steps appear once the patient is admitted.');
            return;
        }
        const discharged = (frm.doc.status === 'Discharged');
        frappe.call({
            method: 'inpatient_patch.inpatient_patch.billing.get_finance_access',
            callback(fr) {
                const canFinance = !!(fr.message);
                frappe.call({
                    method: 'inpatient_patch.inpatient_patch.workflow.get_stage',
                    args: { inpatient_record: frm.doc.name },
                    callback(r) {
                        const s = r.message || {};
                        s._finance = canFinance;
                        s._discharged = discharged;
                        add_create_button(frm, s);
                        render_dashboard(frm, s);
                        show_next_step(frm, s);
                        render_snapshot(frm);
                    },
                });
            },
        });
    },
});

function go(frm, sheet) {
    frappe.route_options = { inpatient_record: frm.doc.name, patient: frm.doc.patient };
    frappe.new_doc(sheet);
}

function open_handover(frm) {
    frappe.call({
        method: 'inpatient_patch.inpatient_patch.nurse_handover.get_or_create_handover',
        args: { inpatient_record: frm.doc.name }, freeze: true,
        freeze_message: __('Opening handover…'),
        callback(r) { if (r.message) frappe.set_route('Form', 'Nurse Handover', r.message); },
    });
}

// Build the list of actions valid for the current stage.
function build_actions(frm, s) {
    const A = [];
    const add = (group, label, fn) => A.push({ group, label, fn });

    if (s._discharged) {
        add('View', 'Care Timeline (notifications)', () => frappe.set_route('List', 'Patient Notification', { inpatient_record: frm.doc.name }));
        add('View', 'Nurse Handover', () => open_handover(frm));
        add('View', 'Invoices', () => frappe.set_route('List', 'Sales Invoice', { custom_inpatient_record: frm.doc.name }));
        return A;
    }

    // ----- Post-admit lock: nothing until the bed invoice is created -----
    if (frm.doc.status === 'Admitted' && !s.bed_billed) {
        if (s._finance) add('Billing', 'Bill Bed Now (required first)', () => bill_bed(frm));
        return A;
    }

    // ----- Admission -----
    if (!s.has_nursing)        add('Admission', 'Nursing Admission Assessment', () => go(frm, 'Nursing Admission Assessment'));
    if (s.has_nursing && !s.has_history) add('Admission', 'History & Clinical Examination', () => go(frm, 'History Clinical Examination'));

    // ----- Ward / Nursing (repeatable) -----
    if (s.has_nursing) {
        add('Ward / Nursing', 'Progress Note', () => go(frm, 'Progress Note'));
        add('Ward / Nursing', 'Doctor Order', () => go(frm, 'Doctor Order'));
        add('Ward / Nursing', 'Medication Administration (MAR)', () => go(frm, 'Medication Administration Record'));
        add('Ward / Nursing', 'Diabetic Insulin Chart', () => go(frm, 'Diabetic Insulin Chart'));
        add('Ward / Nursing', 'Daily Round Plan', () => go(frm, 'Daily Round Plan'));
        add('Ward / Nursing', 'Nurse Handover (dashboard)', () => open_handover(frm));
    }

    // ----- Operation (surgical only) -----
    if (s.is_surgical) {
        if (s.anesthesia_unfit || s.cardiac_not_cleared) {
            const why = s.anesthesia_unfit ? 'the anaesthetist marked this patient UNFIT'
                : 'the Cardiac Review is not cleared (plan is not "Fit for Surgery")';
            add('Operation (OT)', '\u26D4 Cannot operate \u2014 ' + (s.anesthesia_unfit ? 'UNFIT (anaesthesia)' : 'cardiac not cleared'), () =>
                frappe.msgprint({ title: __('Cannot Operate'), indicator: 'red',
                    message: __('The operation cannot proceed because ') + why + '.' }));
        } else {
            if (s.has_history && !s.preop_ready) {
                if (!s.has_cardiac)  add('Operation (OT)', 'Cardiac Review', () => go(frm, 'Pre Operation Cardiac Review'));
                if (!s.has_preanesth) add('Operation (OT)', 'Pre-Anesthetic Assessment', () => go(frm, 'Pre Anesthetic Assessment'));
                if (!s.has_consent)  add('Operation (OT)', 'Surgical Consent Form', () => go(frm, 'Surgical Consent Form'));
                if (!s.has_preop)    add('Operation (OT)', 'Pre-Operative Checklist', () => go(frm, 'Pre Operative Checklist'));
            }
            if (s.preop_ready && !s.operated) {
                if ((frm.doc.procedure_prescription || []).some(r => !r.procedure_created))
                    add('Operation (OT)', 'Create Procedure(s) from Order', () => create_procedures(frm));
                add('Operation (OT)', 'Open Theatre (Clinical Procedure)', () => open_theatre(frm));
                if (!s.has_safety)   add('Operation (OT)', 'Surgical Safety Checklist', () => go(frm, 'Surgical Safety Checklist'));
                if (!s.has_procnote) add('Operation (OT)', 'Operation / Procedure Note (optional)', () => go(frm, 'Operation Procedure Note'));
            }
            if (s.operated) {
                if (!s.has_recovery) add('Operation (OT)', 'Recovery Nurse Record', () => go(frm, 'Recovery Nurse Record'));
                if (!s.has_postop)   add('Operation (OT)', 'Post-Operative Checklist', () => go(frm, 'Post Operative Checklist'));
            }
        }
    }

    // ----- Discharge (dynamic: Schedule Discharge -> Discharge) -----
    const can_discharge = s.is_surgical ? s.has_recovery : s.has_history;
    if (can_discharge && !s.discharged) {
        add('Discharge', 'Discharge Summary', () => go(frm, 'Discharge Summary'));
        if (frm.doc.status === 'Admitted') {
            add('Discharge', 'Schedule Discharge', () => schedule_discharge(frm));
        } else if (frm.doc.status === 'Discharge Scheduled') {
            add('Discharge', 'Discharge Patient', () => do_discharge(frm));
        }
        add('Discharge', 'Mark / Update Sponsor', () => sponsor_dialog(frm));
    }

    // ----- Billing (only for finance/reception/audit roles) -----
    if (s._finance) {
        add('Billing', 'New Service Order (lab / drugs / radiology)', () => go(frm, 'Inpatient Service Order'));
        add('Billing', 'Add Deposit', () => open_deposit_dialog(frm));
        add('Billing', 'Bill Bed Now', () => bill_bed(frm));
    }

    // ----- View -----
    add('View', 'Care Timeline (notifications)', () => frappe.set_route('List', 'Patient Notification', { inpatient_record: frm.doc.name }));
    add('View', 'Invoices', () => frappe.set_route('List', 'Sales Invoice', { custom_inpatient_record: frm.doc.name }));
    return A;
}

function add_create_button(frm, s) {
    const btn = frm.add_custom_button(__('Actions'), () => open_create_menu(frm, s));
    btn.addClass('btn-primary');
}

function open_create_menu(frm, s) {
    const actions = build_actions(frm, s);
    const groups = {};
    actions.forEach((a, i) => { (groups[a.group] = groups[a.group] || []).push({ i, label: a.label }); });

    const META = {
        'Admission':      { c: '#3C3489', ic: 'M12 3l9 6v9a1 1 0 0 1 -1 1h-16a1 1 0 0 1 -1 -1v-9z' },
        'Ward / Nursing': { c: '#0F6E56', ic: 'M8 4h8v4h-8z M6 8h12v12h-12z' },
        'Operation (OT)': { c: '#993C1D', ic: 'M12 3v18 M3 12h18' },
        'Discharge':      { c: '#185FA5', ic: 'M9 21V9l6 -3v15 M5 21h14' },
        'Billing':        { c: '#0e7490', ic: 'M3 7h18v10h-18z M3 11h18' },
        'View':           { c: '#6b7280', ic: 'M2 12s3.5 -7 10 -7s10 7 10 7s-3.5 7 -10 7s-10 -7 -10 -7z M12 9a3 3 0 1 0 0 6a3 3 0 0 0 0 -6z' },
    };
    const svg = (p, c) => '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="' + c +
        '" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" style="flex:0 0 auto"><path d="' + p + '"/></svg>';

    let html = '<style>' +
        '.ipm{padding:2px 2px 6px}' +
        '.ipm-grp{margin:14px 0 6px;display:flex;align-items:center;gap:8px}' +
        '.ipm-grp span{font-weight:700;font-size:11px;letter-spacing:.08em;text-transform:uppercase}' +
        '.ipm-grp .ln{flex:1;height:1px;background:linear-gradient(90deg,var(--ipc),transparent)}' +
        '.ipm-act{display:flex;align-items:center;gap:11px;width:100%;text-align:left;margin:5px 0;padding:11px 13px;' +
        'border:1px solid var(--border-color,#e5e7eb);border-radius:11px;background:var(--fg-color,#fff);' +
        'cursor:pointer;transition:all .13s ease;font-size:13.5px;color:var(--text-color,#1f272e);box-shadow:0 1px 2px rgba(0,0,0,.03)}' +
        '.ipm-act:hover{transform:translateX(3px);box-shadow:0 3px 10px rgba(0,0,0,.10)}' +
        '.ipm-act .lbl{flex:1}' +
        '.ipm-act .chev{opacity:.35}' +
        '</style><div class="ipm">';

    Object.keys(groups).forEach((g) => {
        const m = META[g] || { c: '#6b7280', ic: 'M5 12h14' };
        html += '<div class="ipm-grp" style="--ipc:' + m.c + '">' + svg(m.ic, m.c) +
            '<span style="color:' + m.c + '">' + frappe.utils.escape_html(g) + '</span><div class="ln"></div></div>';
        groups[g].forEach((item) => {
            html += '<div class="ipm-act" data-i="' + item.i + '" style="border-left:3px solid ' + m.c + '">' +
                '<span class="lbl">' + frappe.utils.escape_html(item.label) + '</span>' +
                '<svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6l-6 6"/></svg>' +
                '</div>';
        });
    });
    html += '</div>';

    const d = new frappe.ui.Dialog({ title: __('What would you like to do?'), size: 'small' });
    d.$body.html(html);
    d.$body.find('.ipm-act').on('click', function () {
        const idx = parseInt($(this).attr('data-i'), 10);
        d.hide();
        actions[idx].fn();
    });
    d.show();
}

function bill_bed(frm) {
    frappe.call({
        method: 'inpatient_patch.inpatient_patch.billing.bill_bed_for_record',
        args: { inpatient_record: frm.doc.name }, freeze: true,
        callback(r) { if (r.message) { frappe.show_alert({ message: __('Draft bed invoice {0} created', [r.message]), indicator: 'green' }); frm.reload_doc(); } },
    });
}

function create_procedures(frm) {
    frappe.call({
        method: 'inpatient_patch.inpatient_patch.billing.create_procedures_from_record',
        args: { inpatient_record: frm.doc.name }, freeze: true,
        callback() { frm.reload_doc(); },
    });
}

function open_theatre(frm) {
    // 1) must have an ordered procedure
    const procs = (frm.doc.procedure_prescription || []);
    if (!procs.length) {
        frappe.msgprint({ title: __('No Procedure Prescribed'), indicator: 'red',
            message: __('No procedure has been prescribed for this patient. Add a procedure order first.') });
        return;
    }
    // 2) open existing Clinical Procedure if already created
    frappe.call({
        method: 'frappe.client.get_list',
        args: { doctype: 'Clinical Procedure', filters: { inpatient_record: frm.doc.name }, limit_page_length: 5 },
        callback(r) {
            const rows = r.message || [];
            if (rows.length === 1) { frappe.set_route('Form', 'Clinical Procedure', rows[0].name); return; }
            if (rows.length > 1) { frappe.set_route('List', 'Clinical Procedure', { inpatient_record: frm.doc.name }); return; }
            // 3) none yet -> try to create; server throws if not invoiced/preop/unfit
            frappe.call({
                method: 'inpatient_patch.inpatient_patch.billing.create_procedures_from_record',
                args: { inpatient_record: frm.doc.name }, freeze: true,
                callback(res) {
                    const made = res.message || [];
                    if (made.length) frappe.set_route('Form', 'Clinical Procedure', made[0]);
                    // if nothing was made, the server already showed the reason (not invoiced, etc.)
                },
            });
        },
    });
}

function schedule_discharge(frm) {
    frappe.call({
        method: 'inpatient_patch.inpatient_patch.billing.discharge_overpaid_amount',
        args: { inpatient_record: frm.doc.name },
        callback(r) {
            const extra = flt(r.message || 0);
            const proceed = () => frappe.call({
                method: 'healthcare.healthcare.doctype.inpatient_record.inpatient_record.schedule_discharge',
                args: { args: { patient: frm.doc.patient, inpatient_record: frm.doc.name } },
                freeze: true, freeze_message: __('Scheduling discharge...'),
                callback() { frappe.show_alert({ message: __('Discharge scheduled'), indicator: 'blue' }); frm.reload_doc(); },
            });
            if (extra > 0) {
                frappe.confirm(
                    __('The patient has paid {0} more than invoiced. Create a refund Journal Entry for the extra before scheduling discharge?', [format_currency(extra, frm.doc.currency || 'USD')]),
                    () => frappe.call({
                        method: 'inpatient_patch.inpatient_patch.billing.create_refund_journal_entry',
                        args: { inpatient_record: frm.doc.name, amount: extra }, freeze: true,
                        callback() { proceed(); },
                    }),
                    proceed
                );
            } else { proceed(); }
        },
    });
}

function flt(v) { return parseFloat(v) || 0; }

function do_discharge(frm) {
    frappe.call({
        method: 'healthcare.healthcare.doctype.inpatient_record.inpatient_record.discharge',
        args: { args: { patient: frm.doc.patient, inpatient_record: frm.doc.name } },
        freeze: true, freeze_message: __('Discharging...'),
        callback() { frappe.show_alert({ message: __('Patient discharged'), indicator: 'green' }); frm.reload_doc(); },
        error() { frappe.msgprint(__('Discharge blocked. Settle the bill or mark the patient sponsored.')); },
    });
}

async function sponsor_dialog(frm) {
    const pr = await frappe.db.get_value('Patient', frm.doc.patient, 'customer');
    const customer = pr.message && pr.message.customer;
    if (!customer) { frappe.msgprint(__('This patient has no linked Customer.')); return; }
    const cdoc = await frappe.db.get_doc('Customer', customer);
    frappe.prompt([
        { fieldname: 'is_sponsored', label: __('Patient is Sponsored'), fieldtype: 'Check', default: (cdoc.customer_group && !['Patient', 'Patients'].includes(cdoc.customer_group)) ? 1 : 0 },
        { fieldname: 'customer_group', label: __('Sponsor (Customer Group)'), fieldtype: 'Link', options: 'Customer Group', reqd: 1, default: cdoc.customer_group || '', depends_on: 'is_sponsored' },
        { fieldname: 'customer_details', label: __('Membership Number'), fieldtype: 'Data', default: cdoc.customer_details || '', depends_on: 'is_sponsored' },
    ], async (v) => {
        await frappe.db.set_value('Customer', customer, {
            customer_group: v.customer_group,
            customer_details: v.customer_details,
        });
        frappe.show_alert({ message: __('Sponsor updated on Customer {0}', [customer]), indicator: 'green' });
        frm.reload_doc();
    }, __('Sponsor / Payer Details'), __('Update'));
}

function render_dashboard(frm, s) {
    const d = frm.doc;
    const surgical = s.is_surgical;
    let steps = [
        { key: 'adm', label: 'Admission', done: true },
        { key: 'nurse', label: 'Nursing', done: s.has_nursing },
        { key: 'exam', label: 'Examination', done: s.has_history },
    ];
    if (surgical) {
        steps.push({ key: 'preop', label: 'Pre-Op', done: s.preop_ready });
        steps.push({ key: 'ot', label: 'Theatre', done: s.operated });
        steps.push({ key: 'rec', label: 'Recovery', done: s.has_recovery });
    }
    steps.push({ key: 'disc', label: 'Discharge', done: s.discharged });

    let currentIdx = steps.findIndex((x) => !x.done);
    if (currentIdx === -1) currentIdx = steps.length - 1;

    let stepHtml = '';
    const bedIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><path d="M3 7v11"/><path d="M3 11h18"/><path d="M21 18v-6a2 2 0 0 0 -2 -2h-9v6"/><circle cx="7" cy="11" r="1.5"/></svg>';
    const userIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><circle cx="12" cy="7" r="3"/><path d="M6 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2"/></svg>';
    const tagIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><path d="M9 5h10v10l-6 6l-10 -10z"/><circle cx="9" cy="9" r="1"/></svg>';
    const ctColor = (d.custom_care_type === 'Surgery') ? '#D85A30' : '#0F6E56';
    stepHtml += '<div style="display:flex;flex-wrap:wrap;gap:16px;margin:2px 0 12px;font-size:13px;color:var(--text-muted,#888);">' +
        '<span>' + userIcon + ' ' + frappe.utils.escape_html(d.patient_name || d.patient || '') + '</span>' +
        (d.custom_current_bed ? '<span>' + bedIcon + ' ' + frappe.utils.escape_html(d.custom_current_bed) + '</span>' : '') +
        '<span style="color:' + ctColor + ';font-weight:600;">' + tagIcon + ' ' + frappe.utils.escape_html(d.custom_care_type || 'Treatment') + '</span>' +
        '</div>';
    stepHtml += '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:0;margin:6px 0 14px;">';
    steps.forEach((st, i) => {
        let bg = '#e5e7eb', col = '#6b7280', brd = '#e5e7eb';
        if (st.done) { bg = '#10b981'; col = '#fff'; brd = '#10b981'; }
        if (i === currentIdx && !st.done) { bg = '#f59e0b'; col = '#fff'; brd = '#f59e0b'; }
        stepHtml += '<div style="display:flex;align-items:center;">';
        stepHtml += '<div style="background:' + bg + ';color:' + col + ';border:2px solid ' + brd +
            ';border-radius:18px;padding:5px 14px;font-size:12px;font-weight:600;white-space:nowrap;">' +
            (st.done ? '\u2713 ' : '') + frappe.utils.escape_html(st.label) + '</div>';
        if (i < steps.length - 1) {
            stepHtml += '<div style="width:22px;height:3px;background:' + (st.done ? '#10b981' : '#e5e7eb') + ';"></div>';
        }
        stepHtml += '</div>';
    });
    stepHtml += '</div>';

    const ICON = {
        billed: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/></svg>',
        paid: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><path d="M5 12l5 5l10 -10"/></svg>',
        deposit: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><path d="M12 3l9 6v9a1 1 0 0 1 -1 1h-16a1 1 0 0 1 -1 -1v-9z"/><circle cx="12" cy="12" r="2"/></svg>',
        out: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-3px"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M12 3l9 16h-18z"/></svg>',
    };
    const cards = [
        { label: 'Billed', val: d.custom_total_billed, c1: '#6366f1', c2: '#8b5cf6', ic: ICON.billed },
        { label: 'Paid', val: d.custom_total_paid, c1: '#10b981', c2: '#059669', ic: ICON.paid },
        { label: 'Deposit', val: d.custom_total_deposit, c1: '#0ea5e9', c2: '#0284c7', ic: ICON.deposit },
        { label: 'Outstanding', val: d.custom_outstanding, c1: '#f43f5e', c2: '#e11d48', ic: ICON.out },
    ];
    let cardHtml = '';
    if (s._finance) {
        cardHtml = '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:6px;">';
        cards.forEach((c) => {
            const v = format_currency(c.val || 0, d.currency || 'USD');
            cardHtml += '<div style="flex:1;min-width:120px;background:linear-gradient(135deg,' + c.c1 + ',' + c.c2 +
                ');color:#fff;border-radius:12px;padding:12px 14px;box-shadow:0 2px 6px rgba(0,0,0,.12);">' +
                '<div style="font-size:11px;opacity:.9;text-transform:uppercase;letter-spacing:.05em;">' + c.ic + ' ' + c.label + '</div>' +
                '<div style="font-size:20px;font-weight:700;margin-top:2px;">' + v + '</div></div>';
        });
        cardHtml += '</div>';
    }

    frm.dashboard.add_section(stepHtml + cardHtml, __('Inpatient Overview'));
}

function show_next_step(frm, s) {
    let next;
    if (!s.has_nursing) next = 'Complete the Nursing Admission Assessment (Create → Admission).';
    else if (!s.has_history) next = 'Complete the History & Clinical Examination.';
    else if (s.is_surgical && !s.preop_ready) next = 'Prepare for theatre: finish the Pre-Operative Checklist and tick READY FOR OR.';
    else if (s.is_surgical && !s.operated) next = 'Open the Theatre (Clinical Procedure): Time In, Start, Finish, Report.';
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
            { fieldname: 'amount', label: __('Amount'), fieldtype: 'Currency', reqd: 1 },
            { fieldname: 'mode_of_payment', label: __('Mode of Payment'), fieldtype: 'Link', options: 'Mode of Payment', reqd: 1 },
            { fieldname: 'deposit_to_account', label: __('Deposit To Account (cash/bank)'), fieldtype: 'Link', options: 'Account',
              get_query: () => ({ filters: { is_group: 0, account_type: ['in', ['Bank', 'Cash', 'Receivable']] } }) },
            { fieldname: 'remarks', label: __('Remarks'), fieldtype: 'Small Text' },
        ],
        primary_action_label: __('Save Deposit'),
        primary_action(values) {
            frappe.db.insert({
                doctype: 'Patient Deposit', inpatient_record: frm.doc.name, patient: frm.doc.patient,
                deposit_date: frappe.datetime.now_datetime(), amount: values.amount,
                mode_of_payment: values.mode_of_payment, deposit_to_account: values.deposit_to_account,
                remarks: values.remarks,
            }).then((doc) => {
                frappe.call({ method: 'frappe.client.submit', args: { doc } }).then(() => {
                    d.hide(); frappe.show_alert({ message: __('Deposit recorded'), indicator: 'green' }); frm.reload_doc();
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
            let shown = 0;
            Object.keys(counts).forEach((sheet) => {
                const n = counts[sheet];
                if (!n) return;  // only show sheets that exist; create new via Actions
                const url = '/app/' + frappe.router.slug(sheet) + '?inpatient_record=' + encodeURIComponent(frm.doc.name);
                html += '<a href="' + url + '" style="text-decoration:none;border:1px solid #1f9d55' +
                    ';color:#1f9d55;border-radius:12px;padding:2px 10px;font-size:12px;">' +
                    frappe.utils.escape_html(sheet) + ' : <b>' + n + '</b></a>';
                shown += 1;
            });
            html += '</div>';
            if (shown) frm.dashboard.add_section(html, __('Completed Sheets (click to open)'));
        },
    });
}
