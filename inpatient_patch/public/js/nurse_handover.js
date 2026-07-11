// Nurse Handover - elegant per-patient dashboard rendered into board_html.
frappe.ui.form.on('Nurse Handover', {
    validate(frm) {
        (frm.doc.shift_handovers || []).forEach((r) => {
            if (r.acknowledged && !r.acknowledged_at) r.acknowledged_at = frappe.datetime.now_datetime();
        });
    },
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__('Refresh Data'), () => render(frm)).addClass('btn-primary');
        frm.add_custom_button(__('Add Shift Handover'), () => add_shift(frm));
        if (frm.doc.inpatient_record) {
            frm.add_custom_button(__('Open Inpatient Record'), () =>
                frappe.set_route('Form', 'Inpatient Record', frm.doc.inpatient_record), __('View'));
        }
        render(frm);
    },
});

function add_shift(frm) {
    frappe.call({ method: 'inpatient_patch.inpatient_patch.handover_board.session_nurse_and_shift',
        callback(r) {
            const m = r.message || {};
            const row = frm.add_child('shift_handovers');
            row.nurse = m.nurse; row.shift = m.shift;
            row.handover_datetime = frappe.datetime.now_datetime();
            frm.refresh_field('shift_handovers');
            frm.scroll_to_field('shift_handovers');
        } });
}

function esc(v) { return frappe.utils.escape_html(v == null ? '' : String(v)); }

function render(frm) {
    const wrap = frm.fields_dict.board_html && frm.fields_dict.board_html.$wrapper;
    if (!wrap) return;
    wrap.html('<div class="text-muted" style="padding:10px">Loading dashboard…</div>');
    frappe.call({
        method: 'inpatient_patch.inpatient_patch.handover_board.patient_shift_detail',
        args: { inpatient_record: frm.doc.inpatient_record },
        callback(r) { wrap.html(build(frm, r.message || {})); },
    });
}

const CSS = `<style>
.nh{--r:14px}
.nh-hero{display:flex;flex-wrap:wrap;gap:14px;align-items:center;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border-radius:var(--r);padding:16px 18px;margin-bottom:14px}
.nh-hero .av{width:52px;height:52px;border-radius:50%;background:rgba(255,255,255,.2);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px}
.nh-hero h3{margin:0;font-size:19px}
.nh-hero .sub{opacity:.9;font-size:12.5px}
.nh-hero .st{margin-left:auto;text-align:right}
.nh-badge{background:rgba(255,255,255,.22);border-radius:20px;padding:3px 12px;font-weight:700;font-size:12px}
.nh-cards{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}
.nh-card{flex:1;min-width:120px;color:#fff;border-radius:var(--r);padding:12px 14px;box-shadow:0 3px 10px rgba(0,0,0,.10)}
.nh-card .l{font-size:10.5px;opacity:.92;text-transform:uppercase;letter-spacing:.05em}
.nh-card .n{font-size:22px;font-weight:800}
.nh-sec{border:1px solid var(--border-color,#e6e9ec);border-radius:var(--r);padding:14px 16px;margin-bottom:12px;background:var(--card-bg,#fff)}
.nh-sec h5{margin:0 0 10px;font-size:13.5px;font-weight:800;color:var(--heading-color,#33404d);display:flex;gap:7px;align-items:center}
.nh table{width:100%;border-collapse:collapse;font-size:12px}
.nh th{text-align:left;color:var(--text-muted,#7b8794);font-weight:600;padding:4px 8px;border-bottom:1px solid var(--border-color,#eef0f2)}
.nh td{padding:5px 8px;border-bottom:1px solid var(--border-color,#f2f4f6)}
.nh-prio{background:#fff7ed;border:1px solid #fed7aa;border-radius:var(--r);padding:12px 16px;margin-bottom:14px}
.nh-prio h5{color:#c2410c;margin:0 0 6px}
.nh-prio li{margin:3px 0;font-size:13px}
.nh-empty{color:var(--text-muted,#9aa4ad);font-size:12px;font-style:italic}
.nh-disc{color:#b91c1c}
</style>`;

function spark(vals, color, label, unit) {
    const nums = (vals || []).filter((v) => v != null && v !== '' && !isNaN(parseFloat(v))).map(parseFloat);
    if (!nums.length) return '';
    const w = 260, h = 54, pad = 6, mn = Math.min.apply(null, nums), mx = Math.max.apply(null, nums), rg = (mx - mn) || 1;
    const step = nums.length > 1 ? (w - 2 * pad) / (nums.length - 1) : 0;
    let d = '', dots = '';
    nums.forEach((n, i) => { const x = pad + i * step, y = h - pad - ((n - mn) / rg) * (h - 2 * pad); d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1) + ' '; dots += '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="2.2" fill="' + color + '"/>'; });
    return '<div style="margin:6px 0"><div style="font-size:11.5px;color:var(--text-muted,#7b8794)">' + label + ' · latest <b style="color:' + color + '">' + nums[nums.length - 1] + (unit || '') + '</b> <span style="opacity:.7">(min ' + mn + ', max ' + mx + ')</span></div><svg width="' + w + '" height="' + h + '"><path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' + dots + '</svg></div>';
}

function build(frm, data) {
    const d = frm.doc;
    const initials = (d.patient_name || '?').split(' ').map((x) => x[0]).slice(0, 2).join('').toUpperCase();
    const meds = data.meds || [], vs = data.vitals || [], g = data.glucose || [];
    const given = meds.filter((m) => m.given), pending = meds.filter((m) => !m.given);
    const disc = meds.filter((m) => (m.status || '').toLowerCase().indexOf('disc') >= 0 || (m.status || '').toLowerCase().indexOf('stop') >= 0);

    let h = CSS + '<div class="nh">';
    h += '<div class="nh-hero"><div class="av">' + esc(initials) + '</div>' +
        '<div><h3>' + esc(d.patient_name || '') + '</h3><div class="sub">' + esc(d.inpatient_record || '') +
        (d.admission_date ? ' · admitted ' + esc(d.admission_date) : '') + (d.responsible_nurse ? ' · nurse ' + esc(d.responsible_nurse) : '') + '</div></div>' +
        '<div class="st"><span class="nh-badge">' + esc(d.status || 'Open') + '</span></div></div>';

    h += '<div class="nh-cards">' +
        card('Meds Given', given.length, '#10b981') +
        card('Meds Pending', pending.length, '#f43f5e') +
        card('Vitals Records', vs.length, '#6366f1') +
        card('Glucose Reads', g.length, '#16a34a') + '</div>';

    h += '<div class="nh-prio"><h5>⚑ Priority — pending for this nurse</h5><ul>';
    let any = false;
    pending.forEach((m) => { any = true; h += '<li>💊 Give <b>' + esc(m.drug) + '</b> ' + esc(m.dose ? '(' + m.dose + ')' : '') + (m.time ? ' — due ' + esc(m.time) : '') + '</li>'; });
    if (!vs.length) { any = true; h += '<li>❤️ No vitals recorded yet — take a set.</li>'; }
    if (!any) h += '<li class="nh-empty">Nothing pending. Good to hand over.</li>';
    h += '</ul></div>';

    h += sec('💊 Medicines Given', meds.length ? table(['Drug', 'Dose/grams', 'Time', 'Nurse', 'Status'],
        meds.map((m) => [esc(m.drug), esc(m.dose), esc(m.time), esc(m.nurse), (m.given ? 'Given ✅' : 'Pending ⏳')])) : empty('No medications recorded.'));

    h += sec('🚫 Medicines Discontinued', disc.length ? table(['Drug', 'Note'],
        disc.map((m) => ['<span class="nh-disc">' + esc(m.drug) + '</span>', esc(m.status)])) : empty('None discontinued.'));

    let vsec = '';
    if (vs.length) {
        vsec += '<div style="display:flex;flex-wrap:wrap;gap:18px"><div>' + spark(vs.map((v) => v.pulse), '#e11d48', 'Pulse', '/min') + spark(vs.map((v) => v.temperature), '#f59e0b', 'Temp', '°') + '</div><div>' + spark(vs.map((v) => v.bp_systolic), '#6366f1', 'BP Systolic', '') + spark(vs.map((v) => v.oxygen_saturation), '#0ea5e9', 'SpO2', '%') + '</div></div>';
        vsec += table(['Date', 'BP', 'Pulse', 'Temp', 'RR', 'SpO2'], vs.slice(-6).map((v) => [esc(v.signs_date), esc((v.bp_systolic || '-') + '/' + (v.bp_diastolic || '-')), esc(v.pulse || '-'), esc(v.temperature || '-'), esc(v.respiratory_rate || '-'), esc(v.oxygen_saturation || '-')]));
    } else vsec = empty('No vitals recorded.');
    h += sec('❤️ Vital Signs & Progress', vsec);

    let gsec = '';
    if (g.length) { gsec += spark(g.map((x) => x.glucose), '#16a34a', 'Blood Glucose', ''); gsec += table(['Time', 'Glucose', 'Insulin'], g.slice(-8).map((x) => [esc(x.time), esc(x.glucose), esc(x.insulin)])); }
    else gsec = empty('No glucose readings.');
    h += sec('🩸 Diabetic Chart', gsec);

    h += '</div>';
    return h;
}

function card(l, n, c) { return '<div class="nh-card" style="background:linear-gradient(135deg,' + c + ',' + c + 'cc)"><div class="l">' + l + '</div><div class="n">' + n + '</div></div>'; }
function sec(title, inner) { return '<div class="nh-sec"><h5>' + title + '</h5>' + inner + '</div>'; }
function empty(t) { return '<div class="nh-empty">' + t + '</div>'; }
function table(cols, rows) {
    let h = '<table><thead><tr>' + cols.map((c) => '<th>' + c + '</th>').join('') + '</tr></thead><tbody>';
    rows.forEach((r) => { h += '<tr>' + r.map((c) => '<td>' + c + '</td>').join('') + '</tr>'; });
    return h + '</tbody></table>';
}
