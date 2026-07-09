// Auto-fill the session nurse + her current shift on nurse-entry doctypes.
function _nurse_defaults(frm) {
    if (!frm.is_new()) return;
    frappe.call({ method: 'inpatient_patch.inpatient_patch.handover_board.session_nurse_and_shift',
        callback(r) {
            const m = r.message || {};
            if (m.nurse && frm.fields_dict.recording_nurse && !frm.doc.recording_nurse) frm.set_value('recording_nurse', m.nurse);
            if (m.shift && frm.fields_dict.shift && !frm.doc.shift) frm.set_value('shift', m.shift);
        } });
}
frappe.ui.form.on('Diabetic Insulin Chart', { onload: _nurse_defaults });
