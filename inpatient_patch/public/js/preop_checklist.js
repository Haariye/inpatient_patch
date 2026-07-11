// Pre Operative Checklist: pull diagnosis (multiselect) + procedure from the
// linked Inpatient Record so the nurse does not re-type them.
frappe.ui.form.on('Pre Operative Checklist', {
    onload(frm) { if (frm.doc.inpatient_record) pull_from_record(frm); },
    inpatient_record(frm) { pull_from_record(frm); },
});

function pull_from_record(frm) {
    if (!frm.doc.inpatient_record) return;
    frappe.db.get_doc('Inpatient Record', frm.doc.inpatient_record).then((ip) => {
        // diagnosis -> Table MultiSelect (Patient Encounter Diagnosis)
        if ((ip.diagnosis || []).length && !(frm.doc.diagnosis || []).length) {
            frm.clear_table('diagnosis');
            ip.diagnosis.forEach((d) => {
                const row = frm.add_child('diagnosis');
                row.diagnosis = d.diagnosis || d.diagnosis_name || d.value;
            });
            frm.refresh_field('diagnosis');
        }
        // procedure -> read-only text from procedure_prescription
        const procs = (ip.procedure_prescription || [])
            .map((x) => x.procedure_name || x.procedure).filter(Boolean);
        if (procs.length && !frm.doc.procedure) {
            frm.set_value('procedure', procs.join(', '));
        }
    });
}
