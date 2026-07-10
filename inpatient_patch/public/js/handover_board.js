// Nurse Handover Board - one rich, editable section per patient.
frappe.ui.form.on('Nurse Handover Board', {
    onload(frm) {
        frm.set_df_property('patients', 'hidden', 1);
        if (frm.is_new() && !frm.doc.responsible_nurse) {
            frappe.call({ method: 'inpatient_patch.inpatient_patch.handover_board.session_nurse_and_shift',
                callback(r) { if (r.message && r.message.nurse) frm.set_value('responsible_nurse', r.message.nurse); } });
        }
    },
    refresh(frm) {
        frm.set_df_property('patients', 'hidden', 1);
        if (frm.is_new()) return;
        const M = 'inpatient_patch.inpatient_patch.handover_board.';
        frm.add_custom_button(__('Generate Shift Board'), () => _call(frm, M + 'generate_shift_board')).addClass('btn-primary');
        frm.add_custom_button(__('Pull Latest Data'), () => _call(frm, M + 'pull_latest_data'));
        if (frm.doc.status === 'Open') frm.add_custom_button(__('Wrap Shift \u2192 Next'), () => _call(frm, M + 'wrap_shift'));
        if (frm.doc.status === 'Wrapped') frm.add_custom_button(__('Accept Handover'), () => _call(frm, M + 'accept_handover')).addClass('btn-success');
        render_board(frm);
    },
});

function _call(frm, method) {
    frappe.call({ method, args: { board: frm.doc.name }, freeze: true, callback() { frm.reload_doc(); } });
}

const NHB_CSS = `
<style>
.nhb2{--r:14px}
.nhb2 *{box-sizing:border-box}
.nhb2-head{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:2px 0 14px}
.nhb2-badge{color:#fff;border-radius:20px;padding:4px 14px;font-weight:700;font-size:12px;letter-spacing:.03em}
.nhb2-meta{color:var(--text-muted,#7b8794);font-size:12.5px}
.nhb2-cards{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px}
.nhb2-card{flex:1;min-width:120px;color:#fff;border-radius:var(--r);padding:13px 15px;box-shadow:0 3px 10px rgba(0,0,0,.10)}
.nhb2-card .l{font-size:10.5px;opacity:.92;text-transform:uppercase;letter-spacing:.06em}
.nhb2-card .n{font-size:23px;font-weight:800;margin-top:2px}
.nhb2-pt{border:1px solid var(--border-color,#e6e9ec);border-radius:var(--r);margin-bottom:12px;overflow:hidden;background:var(--card-bg,#fff);box-shadow:0 1px 3px rgba(0,0,0,.04)}
.nhb2-pt.crit{border-color:#f2b8c2}
.nhb2-pth{display:flex;align-items:center;gap:12px;padding:13px 16px;cursor:pointer;user-select:none}
.nhb2-pth:hover{background:var(--control-bg,#f7f8f9)}
.nhb2-av{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:15px;flex:0 0 auto}
.nhb2-nm{font-weight:700;font-size:14.5px}
.nhb2-sub{font-size:11.5px;color:var(--text-muted,#7b8794)}
.nhb2-tags{margin-left:auto;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.nhb2-pill{border-radius:20px;padding:2px 10px;font-size:11px;font-weight:700}
.nhb2-chev{transition:transform .15s;color:var(--text-muted,#7b8794)}
.nhb2-pt.open .nhb2-chev{transform:rotate(90deg)}
.nhb2-body{display:none;padding:0 16px 16px;border-top:1px solid var(--border-color,#eef0f2)}
.nhb2-pt.open .nhb2-body{display:block}
.nhb2-grid{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.nhb2-stat{flex:1;min-width:90px;background:var(--control-bg,#f4f6f8);border-radius:10px;padding:9px 11px}
.nhb2-stat .l{font-size:10px;color:var(--text-muted,#7b8794);text-transform:uppercase}
.nhb2-stat .n{font-size:18px;font-weight:800}
.nhb2-sec{margin-top:12px}
.nhb2-sec h6{margin:0 0 6px;font-size:12.5px;font-weight:800;color:var(--heading-color,#33404d);display:flex;align-items:center;gap:6px}
.nhb2 table{width:100%;border-collapse:collapse;font-size:12px}
.nhb2 table th{text-align:left;color:var(--text-muted,#7b8794);font-weight:600;padding:4px 8px;border-bottom:1px solid var(--border-color,#eef0f2)}
.nhb2 table td{padding:5px 8px;border-bottom:1px solid var(--border-color,#f2f4f6)}
.nhb2-edit{margin-top:14px;padding:12px;border:1px dashed var(--border-color,#d7dbdf);border-radius:12px;background:var(--control-bg,#fafbfc)}
.nhb2-edit label{font-size:11px;color:var(--text-muted,#7b8794);text-transform:uppercase;letter-spacing:.04em}
.nhb2-empty{color:var(--text-muted,#9aa4ad);font-size:12px;font-style:italic}
</style>`;

function _condColor(c){ return (c==='Critical')?'#e11d48':(c==='Guarded')?'#f59e0b':(c==='Improving')?'#0ea5e9':'#059669'; }

function render_board(frm) {
    const d = frm.doc, esc = frappe.utils.escape_html;
    const badge = { Open:'#10b981', Wrapped:'#f59e0b', Accepted:'#3b82f6' }[d.status] || '#6b7280';
    const cards = [
        { l:'Patients', v:d.total_patients||0, c:'#6366f1' },
        { l:'Accepted', v:d.completed_count||0, c:'#10b981' },
        { l:'Pending Meds', v:d.pending_meds_count||0, c:'#f43f5e' },
        { l:'Pending Orders', v:d.pending_tasks_count||0, c:'#f59e0b' },
    ];
    let h = NHB_CSS + '<div class="nhb2">';
    h += '<div class="nhb2-head"><span class="nhb2-badge" style="background:'+badge+'">'+esc(d.status||'Open')+'</span>'+
        (d.responsible_nurse?'<span class="nhb2-meta"><b>Nurse:</b> '+esc(d.responsible_nurse)+'</span>':'')+
        '<span class="nhb2-meta"><b>Shift:</b> '+esc(d.shift||'-')+'</span>'+
        '<span class="nhb2-meta"><b>Date:</b> '+esc(d.handover_date||'-')+'</span>'+
        (d.last_updated?'<span class="nhb2-meta">Updated '+frappe.datetime.comment_when(d.last_updated)+'</span>':'')+'</div>';
    h += '<div class="nhb2-cards">';
    cards.forEach(c=>{ h+='<div class="nhb2-card" style="background:linear-gradient(135deg,'+c.c+','+c.c+'cc)"><div class="l">'+c.l+'</div><div class="n">'+c.v+'</div></div>'; });
    h += '</div>';

    const pts = d.patients || [];
    if (!pts.length) h += '<div class="nhb2-empty">No patients yet. Click <b>Generate Shift Board</b> to load your admitted patients.</div>';
    pts.forEach((r, i) => {
        const cond = r.condition || 'Stable', cc = _condColor(cond);
        const initials = (r.patient_name||'?').split(' ').map(x=>x[0]).slice(0,2).join('').toUpperCase();
        h += '<div class="nhb2-pt'+(cond==='Critical'?' crit':'')+'" data-i="'+i+'" data-ir="'+esc(r.inpatient_record)+'">'+
            '<div class="nhb2-pth">'+
              '<div class="nhb2-av">'+esc(initials)+'</div>'+
              '<div><div class="nhb2-nm">'+esc(r.patient_name||r.patient||'')+'</div>'+
                '<div class="nhb2-sub">'+esc(r.bed_no||'-')+' \u00b7 '+esc(r.inpatient_record||'')+'</div></div>'+
              '<div class="nhb2-tags">'+
                '<span class="nhb2-pill" style="background:'+cc+'22;color:'+cc+'">'+esc(cond)+'</span>'+
                '<span class="nhb2-pill" style="background:#6366f122;color:#6366f1">M '+(r.pending_meds_count||0)+'</span>'+
                '<span class="nhb2-pill" style="background:#f59e0b22;color:#b45309">O '+(r.pending_tasks_count||0)+'</span>'+
                '<span class="nhb2-pill" style="background:#e5e7eb;color:#374151">'+esc(r.handover_status||'Pending')+'</span>'+
                '<svg class="nhb2-chev" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6l-6 6"/></svg>'+
              '</div>'+
            '</div>'+
            '<div class="nhb2-body" id="nhb2-body-'+i+'"><div class="nhb2-empty">Loading\u2026</div></div>'+
          '</div>';
    });
    h += '</div>';

    frm.dashboard.clear();
    const target = (frm.fields_dict.board_view && frm.fields_dict.board_view.$wrapper);
    if (target && target.length) { target.html(h); }
    else { frm.dashboard.add_section(h, __('Shift Handover')); }
    const wrap = (target && target.length) ? target : frm.dashboard.wrapper;
    wrap.find('.nhb2-pth').on('click', function () {
        const card = $(this).closest('.nhb2-pt');
        card.toggleClass('open');
        if (card.hasClass('open') && !card.data('loaded')) {
            card.data('loaded', 1);
            load_section(frm, card.data('ir'), card.data('i'), card.find('.nhb2-body'));
        }
    });
}

function load_section(frm, ir, idx, body) {
    const row = (frm.doc.patients || [])[idx] || {};
    const esc = frappe.utils.escape_html;
    frappe.call({
        method: 'inpatient_patch.inpatient_patch.handover_board.patient_shift_detail',
        args: { inpatient_record: ir },
        callback(r) {
            const data = r.message || {};
            let h = '<div class="nhb2-grid">'+
                _stat('Meds Given', row.meds_given_count||0)+
                _stat('Meds Pending', row.pending_meds_count||0)+
                _stat('Orders/Tasks', row.pending_tasks_count||0)+
                _stat('Last Vitals', esc(row.latest_vitals||'-'), true)+
            '</div>';
            if (row.alerts_summary) h += '<div style="background:#fef2f2;border:1px solid #f2c0c0;color:#b91c1c;border-radius:10px;padding:8px 12px;font-size:12.5px;margin-bottom:8px">\u26A0 '+esc(row.alerts_summary)+'</div>';
            h += render_rich(data);
            // editable handover block
            h += '<div class="nhb2-edit">'+
                '<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end">'+
                  '<div><label>Condition</label><br><select class="form-control input-sm nhb2-cond" style="width:170px">'+
                    ['Stable','Improving','Guarded','Critical'].map(o=>'<option'+(row.condition===o?' selected':'')+'>'+o+'</option>').join('')+'</select></div>'+
                  '<div style="flex:1;min-width:220px"><label>Nurse Notes (handover)</label>'+
                    '<textarea class="form-control nhb2-notes" rows="2">'+esc(row.nurse_notes||'')+'</textarea></div>'+
                '</div>'+
                '<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">'+
                  '<button class="btn btn-sm btn-primary nhb2-save">'+__('Save Handover')+'</button>'+
                  '<button class="btn btn-sm btn-default nhb2-mar">'+__('Open MAR')+'</button>'+
                  '<button class="btn btn-sm btn-default nhb2-vit">'+__('Vitals')+'</button>'+
                  '<button class="btn btn-sm btn-default nhb2-prog">'+__('Progress')+'</button>'+
                  '<button class="btn btn-sm btn-default nhb2-ir">'+__('Open Record')+'</button>'+
                '</div></div>';
            body.html(h);
            body.find('.nhb2-save').on('click', () => {
                frappe.model.set_value(row.doctype, row.name, 'condition', body.find('.nhb2-cond').val());
                frappe.model.set_value(row.doctype, row.name, 'nurse_notes', body.find('.nhb2-notes').val());
                frappe.model.set_value(row.doctype, row.name, 'handover_status', 'In Progress');
                frm.save().then(() => frappe.show_alert({ message: __('Handover saved'), indicator: 'green' }));
            });
            const openList = (dt) => frappe.set_route('List', dt, { inpatient_record: ir });
            body.find('.nhb2-mar').on('click', () => openList('Medication Administration Record'));
            body.find('.nhb2-vit').on('click', () => openList('Vital Signs'));
            body.find('.nhb2-prog').on('click', () => openList('Progress Note'));
            body.find('.nhb2-ir').on('click', () => frappe.set_route('Form', 'Inpatient Record', ir));
        },
    });
}

function _stat(l, v, small) {
    return '<div class="nhb2-stat"><div class="l">'+l+'</div><div class="n"'+(small?' style="font-size:13px;font-weight:700"':'')+'>'+v+'</div></div>';
}

function _sparkline(values, color, label, unit) {
    const nums = values.filter(v => v!=null && v!=='' && !isNaN(parseFloat(v))).map(parseFloat);
    if (!nums.length) return '';
    const w=260,h=54,pad=6, min=Math.min.apply(null,nums), max=Math.max.apply(null,nums), rng=(max-min)||1;
    const step = nums.length>1 ? (w-2*pad)/(nums.length-1) : 0;
    let d='', pts='';
    nums.forEach((n,i)=>{ const x=pad+i*step, y=h-pad-((n-min)/rng)*(h-2*pad); d+=(i===0?'M':'L')+x.toFixed(1)+' '+y.toFixed(1)+' '; pts+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="2.2" fill="'+color+'"/>'; });
    const last = nums[nums.length-1];
    return '<div style="margin:8px 0"><div style="font-size:11.5px;color:var(--text-muted,#7b8794)">'+label+
        ' \u00b7 latest <b style="color:'+color+'">'+last+(unit||'')+'</b> <span style="opacity:.7">(min '+min+', max '+max+')</span></div>'+
        '<svg width="'+w+'" height="'+h+'"><path d="'+d+'" fill="none" stroke="'+color+'" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'+pts+'</svg></div>';
}

function render_rich(data) {
    const esc = frappe.utils.escape_html;
    let h = '';
    // Medications
    h += '<div class="nhb2-sec"><h6>\uD83D\uDC8A Medications</h6>';
    if ((data.meds||[]).length) {
        h += '<table><thead><tr><th>Drug</th><th>Dose / grams</th><th>Time</th><th>Nurse</th><th>Given</th></tr></thead><tbody>';
        data.meds.forEach(m=>{ h+='<tr><td>'+esc(m.drug)+'</td><td>'+esc(m.dose)+'</td><td>'+esc(m.time)+'</td><td>'+esc(m.nurse)+'</td><td>'+(m.given?'\u2705':'\u23F3')+'</td></tr>'; });
        h += '</tbody></table>';
    } else h += '<div class="nhb2-empty">No medications recorded.</div>';
    h += '</div>';
    // Vitals + charts
    h += '<div class="nhb2-sec"><h6>\u2764\uFE0F Vital Signs</h6>';
    const vs = data.vitals||[];
    if (vs.length) {
        h += '<div style="display:flex;flex-wrap:wrap;gap:18px">';
        h += '<div>'+_sparkline(vs.map(v=>v.pulse),'#e11d48','Pulse','/min')+_sparkline(vs.map(v=>v.temperature),'#f59e0b','Temp','\u00b0')+'</div>';
        h += '<div>'+_sparkline(vs.map(v=>v.bp_systolic),'#6366f1','BP Systolic','')+_sparkline(vs.map(v=>v.oxygen_saturation),'#0ea5e9','SpO2','%')+'</div>';
        h += '</div><table><thead><tr><th>Date</th><th>BP</th><th>Pulse</th><th>Temp</th><th>RR</th><th>SpO2</th></tr></thead><tbody>';
        vs.slice(-6).forEach(v=>{ h+='<tr><td>'+esc(v.signs_date||'')+'</td><td>'+esc((v.bp_systolic||'-')+'/'+(v.bp_diastolic||'-'))+'</td><td>'+esc(v.pulse||'-')+'</td><td>'+esc(v.temperature||'-')+'</td><td>'+esc(v.respiratory_rate||'-')+'</td><td>'+esc(v.oxygen_saturation||'-')+'</td></tr>'; });
        h += '</tbody></table>';
    } else h += '<div class="nhb2-empty">No vitals recorded.</div>';
    h += '</div>';
    // Glucose
    h += '<div class="nhb2-sec"><h6>\uD83E\uDE78 Glucose / Insulin</h6>';
    const g = data.glucose||[];
    if (g.length) {
        h += _sparkline(g.map(x=>x.glucose),'#16a34a','Blood Glucose','');
        h += '<table><thead><tr><th>Time</th><th>Glucose</th><th>Insulin</th></tr></thead><tbody>';
        g.slice(-8).forEach(x=>{ h+='<tr><td>'+esc(x.time)+'</td><td>'+esc(x.glucose)+'</td><td>'+esc(x.insulin)+'</td></tr>'; });
        h += '</tbody></table>';
    } else h += '<div class="nhb2-empty">No glucose readings.</div>';
    h += '</div>';
    return h;
}
