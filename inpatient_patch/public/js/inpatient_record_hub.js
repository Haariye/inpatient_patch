// Inpatient Record hub: ONE "Create" button opens a grouped menu of the
// actions that are valid right now (gated, and hidden once a step is done).
// A "Next step" banner guides staff; the Clinical Sheets badges are live links.

frappe.ui.form.on('Inpatient Record', {
    refresh(frm) {
        if (frm.is_new()) return;
        frappe.call({
            method: 'inpatient_patch.inpatient_patch.workflow.get_stage',
            args: { inpatient_record: frm.doc.name },
            callback(r) {
                const s = r.message || {};
                add_create_button(frm, s);
                render_dashboard(frm, s);
                show_next_step(frm, s);
                render_snapshot(frm);
            },
        });
    },
});

function go(frm, sheet) {
    frappe.route_options = { inpatient_record: frm.doc.name, patient: frm.doc.patient };
    frappe.new_doc(sheet);
}

// Build the list of actions valid for the current stage.
function build_actions(frm, s) {
    const A = [];
    const add = (group, label, fn) => A.push({ group, label, fn });

    // ----- Admission -----
    if (!s.has_admission_data) add('Admission', 'Admission Social Data', () => go(frm, 'Admission Social Data'));
    if (!s.has_nursing)        add('Admission', 'Nursing Admission Assessment', () => go(frm, 'Nursing Admission Assessment'));
    if (s.has_nursing && !s.has_history) add('Admission', 'History & Clinical Examination', () => go(frm, 'History Clinical Examination'));

    // ----- Ward / Nursing (repeatable) -----
    if (s.has_nursing) {
        add('Ward / Nursing', 'Progress Note', () => go(frm, 'Progress Note'));
        add('Ward / Nursing', 'Doctor Order', () => go(frm, 'Doctor Order'));
        add('Ward / Nursing', 'Medication Administration (MAR)', () => go(frm, 'Medication Administration Record'));
        add('Ward / Nursing', 'Diabetic Insulin Chart', () => go(frm, 'Diabetic Insulin Chart'));
        add('Ward / Nursing', 'Daily Round Plan', () => go(frm, 'Daily Round Plan'));
        add('Ward / Nursing', 'Nurse Handover', () => go(frm, 'Nurse Handover'));
    }

    // ----- Operation (surgical only) -----
    if (s.is_surgical) {
        if (s.has_history && !s.preop_ready) {
            add('Operation (OT)', 'Cardiac Review', () => go(frm, 'Pre Operation Cardiac Review'));
            add('Operation (OT)', 'Pre-Anesthetic Assessment', () => go(frm, 'Pre Anesthetic Assessment'));
            if (!s.has_consent) add('Operation (OT)', 'Surgical Consent Form', () => go(frm, 'Surgical Consent Form'));
            add('Operation (OT)', 'Pre-Operative Checklist', () => go(frm, 'Pre Operative Checklist'));
        }
        if (s.preop_ready && !s.operated) {
            add('Operation (OT)', 'Operation Theatre Case', () => go(frm, 'Operation Theatre Case'));
            add('Operation (OT)', 'Surgical Safety Checklist', () => go(frm, 'Surgical Safety Checklist'));
            add('Operation (OT)', 'OR Tracking Board', () => go(frm, 'OR Tracking Board'));
            add('Operation (OT)', 'Operation / Procedure Note', () => go(frm, 'Operation Procedure Note'));
        }
        if (s.operated) {
            if (!s.has_recovery) add('Operation (OT)', 'Recovery Nurse Record', () => go(frm, 'Recovery Nurse Record'));
            if (!s.has_postop)   add('Operation (OT)', 'Post-Operative Checklist', () => go(frm, 'Post Operative Checklist'));
        }
    }

    // ----- Discharge -----
    const can_discharge = s.is_surgical ? s.has_recovery : s.has_history;
    if (can_discharge && !s.discharged) add('Discharge', 'Discharge Summary', () => go(frm, 'Discharge Summary'));

    // ----- Billing -----
    add('Billing', 'Send Service to Billing (lab / drugs / radiology)', () => go(frm, 'Inpatient Service Order'));
    add('Billing', 'Add Deposit', () => open_deposit_dialog(frm));
    add('Billing', 'Bill Bed Now', () => bill_bed(frm));

    // ----- View -----
    add('View', 'Care Timeline (notifications)', () => frappe.set_route('List', 'Patient Notification', { inpatient_record: frm.doc.name }));
    add('View', 'Nurse Handovers', () => frappe.set_route('List', 'Nurse Handover', { inpatient_record: frm.doc.name }));
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

    let html = '<div class="ip-create-menu">';
    Object.keys(groups).forEach((g) => {
        html += '<div style="margin:6px 0 2px;font-weight:600;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.04em;">' + frappe.utils.escape_html(g) + '</div>';
        groups[g].forEach((item) => {
            html += '<button type="button" class="btn btn-default btn-sm ip-act" data-i="' + item.i +
                '" style="display:block;width:100%;text-align:left;margin:3px 0;">' +
                frappe.utils.escape_html(item.label) + '</button>';
        });
    });
    html += '</div>';

    const d = new frappe.ui.Dialog({ title: __('What would you like to do?'), size: 'small' });
    d.$body.html(html);
    d.$body.find('.ip-act').on('click', function () {
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

    let stepHtml = '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:0;margin:6px 0 14px;">';
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

    const cards = [
        { label: 'Billed', val: d.custom_total_billed, c1: '#6366f1', c2: '#8b5cf6' },
        { label: 'Paid', val: d.custom_total_paid, c1: '#10b981', c2: '#059669' },
        { label: 'Deposit', val: d.custom_total_deposit, c1: '#0ea5e9', c2: '#0284c7' },
        { label: 'Outstanding', val: d.custom_outstanding, c1: '#f43f5e', c2: '#e11d48' },
    ];
    let cardHtml = '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:6px;">';
    cards.forEach((c) => {
        const v = format_currency(c.val || 0, d.currency || 'USD');
        cardHtml += '<div style="flex:1;min-width:120px;background:linear-gradient(135deg,' + c.c1 + ',' + c.c2 +
            ');color:#fff;border-radius:12px;padding:12px 14px;box-shadow:0 2px 6px rgba(0,0,0,.12);">' +
            '<div style="font-size:11px;opacity:.9;text-transform:uppercase;letter-spacing:.05em;">' + c.label + '</div>' +
            '<div style="font-size:20px;font-weight:700;margin-top:2px;">' + v + '</div></div>';
    });
    cardHtml += '</div>';

    frm.dashboard.add_section(stepHtml + cardHtml, __('Inpatient Overview'));
}

function show_next_step(frm, s) {
    let next;
    if (!s.has_nursing) next = 'Complete the Nursing Admission Assessment (Create → Admission).';
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
                const color = n ? '#1f9d55' : '#9aa0a6';
                const url = '/app/' + frappe.router.slug(sheet) + '?inpatient_record=' + encodeURIComponent(frm.doc.name);
                html += '<a href="' + url + '" style="text-decoration:none;border:1px solid ' + color +
                    ';color:' + color + ';border-radius:12px;padding:2px 10px;font-size:12px;">' +
                    frappe.utils.escape_html(sheet) + ' : <b>' + n + '</b></a>';
            });
            html += '</div>';
            frm.dashboard.add_section(html, __('Clinical Sheets (click to open)'));
        },
    });
}
