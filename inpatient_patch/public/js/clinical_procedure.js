// Clinical Procedure = the theatre. Buttons drive OR tracking + report.
frappe.ui.form.on('Clinical Procedure', {
    onload(frm) {
        frm.set_query('custom_operation_theatre', () => ({
            query: 'inpatient_patch.inpatient_patch.ot.ot_facility_query',
        }));
    },
    refresh(frm) {
        if (frm.is_new()) return;
        const M = 'inpatient_patch.inpatient_patch.ot.';
        const call = (m) => frappe.call({ method: M + m, args: { clinical_procedure: frm.doc.name }, freeze: true, callback() { frm.reload_doc(); } });
        if (!frm.doc.custom_time_in) frm.add_custom_button(__('1. Time In'), () => call('cp_time_in'), __('Theatre'));
        if (frm.doc.custom_time_in && !frm.doc.custom_surgery_start)
            frm.add_custom_button(__('2. Start Surgery'), () => call('cp_start_surgery'), __('Theatre')).addClass('btn-success');
        if (frm.doc.custom_surgery_start && !frm.doc.custom_surgery_finish)
            frm.add_custom_button(__('3. Finish Surgery'), () => call('cp_finish_surgery'), __('Theatre')).addClass('btn-danger');
        if (frm.doc.custom_surgery_finish && !frm.doc.custom_time_out)
            frm.add_custom_button(__('4. Time Out'), () => call('cp_time_out'), __('Theatre'));
        frm.add_custom_button(__('Generate Operation Report'), () => call('cp_generate_report'), __('Theatre'));
        if (frm.doc.custom_surgery_report) {
            frm.dashboard.add_section(
                '<pre style="white-space:pre-wrap;font-size:12px;background:var(--fg-color,#fff);padding:12px;border-radius:8px;border:1px solid var(--border-color,#eee)">' +
                frappe.utils.escape_html(frm.doc.custom_surgery_report) + '</pre>', __('Operation Report'));
        }
    },
    inpatient_record(frm) {
        if (!frm.doc.inpatient_record) return;
        frappe.db.get_value('Inpatient Record', frm.doc.inpatient_record,
            ['medical_department', 'primary_practitioner']).then((r) => {
                const v = r.message || {};
                if (v.medical_department && !frm.doc.medical_department) frm.set_value('medical_department', v.medical_department);
                if (v.primary_practitioner && !frm.doc.custom_lead_surgeon) frm.set_value('custom_lead_surgeon', v.primary_practitioner);
            });
        // pull anaesthesia decision from the Pre-Anaesthetic Assessment (no re-typing)
        frappe.db.get_list('Pre Anesthetic Assessment', {
            filters: { inpatient_record: frm.doc.inpatient_record },
            fields: ['anesthesia_type', 'anesthetist', 'fitness'],
            order_by: 'modified desc', limit: 1,
        }).then((rows) => {
            if (!rows || !rows.length) return;
            const a = rows[0];
            if (a.fitness && a.fitness.toLowerCase().indexOf('unfit') === 0) {
                frappe.msgprint({ title: __('Unfit for Operation'), indicator: 'red',
                    message: __('The anaesthetist marked this patient UNFIT.') });
            }
            if (a.anesthesia_type && !frm.doc.custom_anesthesia_type) frm.set_value('custom_anesthesia_type', a.anesthesia_type);
            if (a.anesthetist && !frm.doc.custom_anesthetist) frm.set_value('custom_anesthetist', a.anesthetist);
        });
    },
});

// team-member child: Member Type drives which doctype the Name links to
frappe.ui.form.on('OT Team Member', {
    member_type(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        row.member_dt = row.member_type === 'Nurse' ? 'Nurse' : 'Healthcare Practitioner';
        row.member_name = '';
        frm.refresh_field('custom_surgical_team');
    },
    custom_surgical_team_add(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.member_dt) row.member_dt = 'Healthcare Practitioner';
    },
});
