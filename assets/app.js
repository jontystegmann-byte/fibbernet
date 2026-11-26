'use strict';
const $ = (s) => document.querySelector(s);
const form = $('#connection-form'), email = $('#email-form');
let current, initialTemplates, loaded = false, toastTimer, pendingTest = false;
function field(f, name) { return f.elements.namedItem(name); }
function toast(message, error = false) { const el = $('#toast'); el.textContent = message; el.classList.toggle('error', error); el.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, error ? 12000 : 6000); }
async function api(path, data) {
  const options = data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Fibbernet':'1'}, body:JSON.stringify(data)};
  const response = await fetch('/api/' + path, options);
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'The operation failed');
  return result;
}
function fmt(value, digits = 1) { return value == null ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits:digits, minimumFractionDigits:digits}); }
function text(selector, value) { $(selector).textContent = value; }
function set(f, name, value) { const el = field(f, name); if (el.type === 'checkbox') el.checked = !!value; else el.value = value == null ? '' : value; }
function fill(c) {
  for (const name of ['plan_mbps','threshold_mbps','average_hours','minimum_samples','report_days','interface','connection_notes']) set(form, name, c[name]);
  for (const name of ['provider','account_reference']) set(form, name, c.profile[name]);
  for (const name of ['customer_name','user_email','provider_email']) set(email, name, c.profile[name]);
  for (const name of ['host','username','security','port','cooldown_hours','enabled']) set(email, name, c.email[name]);
  set(email,'sender',c.email.from);
  set(email,'target',c.email.to.length && c.email.to[0] === c.profile.provider_email ? 'provider' : 'user');
  set(email,'content',c.email.use_complaint_template ? 'complaint' : 'summary');
  set(email,'subject',c.templates.subject); set(email,'body',c.templates.body);
  $('#hours').replaceChildren();
  for (let h = 0; h < 24; h++) {
    const label = document.createElement('label'); label.className = 'hour';
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.value = h; checkbox.checked = c.hours.includes(h);
    label.append(checkbox, String(h).padStart(2,'0') + ':00'); $('#hours').append(label);
  }
  preview();
}
function settings() {
  const c = structuredClone(current.config);
  for (const name of ['plan_mbps','threshold_mbps','average_hours','minimum_samples','report_days']) c[name] = Number(field(form,name).value);
  for (const name of ['interface','connection_notes']) c[name] = field(form,name).value.trim();
  c.hours = [...$('#hours').querySelectorAll('input:checked')].map(el => Number(el.value));
  for (const name of ['provider','account_reference']) c.profile[name] = field(form,name).value.trim();
  for (const name of ['customer_name','user_email','provider_email']) c.profile[name] = field(email,name).value.trim();
  for (const name of ['host','username','security']) c.email[name] = field(email,name).value.trim();
  c.email.from = field(email,'sender').value.trim();
  c.email.to = [c.profile[field(email,'target').value === 'provider' ? 'provider_email' : 'user_email']].filter(Boolean);
  c.email.enabled = field(email,'enabled').checked;
  c.email.use_complaint_template = field(email,'content').value === 'complaint';
  for (const name of ['port','cooldown_hours']) c.email[name] = Number(field(email,name).value);
  c.templates = {subject:field(email,'subject').value, body:field(email,'body').value};
  return c;
}
function rendered() {
  const c = settings(), rows = current.measurements.filter(r => r.status === 'ok' && Date.now() - Date.parse(r.timestamp_utc) <= c.average_hours*3600000);
  const avg = rows.length ? rows.reduce((a,r)=>a+r.download_mbps,0)/rows.length : null;
  const values = {...c.profile, provider:c.profile.provider || 'your broadband provider', customer_name:c.profile.customer_name || '[your name]', account_reference:c.profile.account_reference || '[account reference]', user_email:c.profile.user_email || '[your email]', plan_mbps:c.plan_mbps, threshold_mbps:c.threshold_mbps, average_mbps:avg == null ? 'No data yet' : avg.toFixed(1), window_hours:c.average_hours, sample_count:rows.length, below_count:rows.filter(r=>r.download_mbps<c.threshold_mbps).length, connection_notes:c.connection_notes || '[connection conditions not recorded]'};
  function expand(template) {
    // Same fixed vocabulary as the engine; no expression evaluation.
    return template.replace(/\{([^{}]*)\}/g, (whole,key) => Object.hasOwn(values,key) ? String(values[key]) : whole);
  }
  return {subject:expand(c.templates.subject), body:expand(c.templates.body), to:c.profile.provider_email};
}
function preview() { if (!current) return; const draft = rendered(); text('#preview-subject',draft.subject); text('#preview-body',draft.body); }
function svgEl(name, attrs, value) { const el = document.createElementNS('http://www.w3.org/2000/svg',name); Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v)); if(value!=null)el.textContent=value; return el; }
function chart(rows,c) {
  const target = $('#chart'); target.replaceChildren();
  const good = rows.filter(r=>r.status==='ok').slice(-100);
  if (!good.length) { const p = document.createElement('p'); p.className='empty'; p.textContent='Your speed history starts with your first test.'; target.append(p); return; }
  const svg = svgEl('svg',{viewBox:'0 0 900 225',role:'presentation'}), max = Math.max(c.plan_mbps,c.threshold_mbps,...good.map(r=>r.download_mbps))*1.12;
  const times = good.map(r=>Date.parse(r.timestamp_utc)), start=times[0], span=times.at(-1)-start;
  const x = t=>span ? 54+(t-start)/span*825 : 466, y = v=>182-v/max*165;
  for (const v of [0,max/2,max]) { const yy=y(v); svg.append(svgEl('line',{x1:54,x2:880,y1:yy,y2:yy,stroke:'#dddcd5'}),svgEl('text',{x:0,y:yy+4},Math.round(v))); }
  svg.append(svgEl('line',{x1:54,x2:880,y1:y(c.threshold_mbps),y2:y(c.threshold_mbps),stroke:'#6b6b68','stroke-dasharray':'5 5'}));
  if (good.length>1) svg.append(svgEl('polyline',{points:good.map((r,i)=>`${x(times[i])},${y(r.download_mbps)}`).join(' '),fill:'none',stroke:'#E11D2A','stroke-width':2.5}));
  good.forEach((r,i)=>{ const dot=svgEl('circle',{cx:x(times[i]),cy:y(r.download_mbps),r:good.length>20?2.5:4,fill:'#E11D2A'}); dot.append(svgEl('title',{},`${new Date(r.timestamp_utc).toLocaleString()}: ${fmt(r.download_mbps)} Mbps`)); svg.append(dot); });
  svg.append(svgEl('text',{x:54,y:216},new Date(start).toLocaleString()),svgEl('text',{x:880,y:216,'text-anchor':'end'},good.length>1?new Date(times.at(-1)).toLocaleString():''));
  target.append(svg);
}
function dashboard(s) {
  const c=s.config;
  text('#average-label',`${c.average_hours}-HOUR DOWNLOAD AVERAGE`);text('#average',fmt(s.average_mbps));text('#plan',fmt(c.plan_mbps,0));
  text('#delivered',s.average_mbps==null?'—':fmt(s.average_mbps/c.plan_mbps*100)+'%');
  text('#average-context',`${s.sample_count} successful ${s.sample_count===1?'test':'tests'} · ${s.sample_count<c.minimum_samples?'collecting enough samples for alerts':s.average_mbps<c.threshold_mbps?'below your '+c.threshold_mbps+' Mbps threshold':'above your alert threshold'}`);
  text('#schedule-status',s.schedule_enabled?'Scheduled daily · '+c.hours.map(h=>String(h).padStart(2,'0')+':00').join(' / '):'Automatic testing is paused');
  const active = s.busy || pendingTest;
  text('#test-status',active?'Testing your connection…':'Measurements stored locally');
  $('#test-button').disabled=active; $('#test-button').textContent=active?'Test in progress…':'Run speed test';
  text('#schedule-toggle',s.schedule_enabled?'Pause automatic tests':'Enable automatic tests');
  text('#last-email',s.last_email_utc?'Last successful automatic email: '+new Date(s.last_email_utc).toLocaleString():'No automatic email has been sent.');
  const body=$('#measurements');body.replaceChildren();
  for(const r of [...s.measurements].reverse().slice(0,50)) {
    const tr=document.createElement('tr');
    const vals=[new Date(r.timestamp_utc).toLocaleString(),fmt(r.download_mbps)+' Mbps',fmt(r.upload_mbps)+' Mbps',fmt(r.latency_ms)+' ms',r.interface||'—',r.status==='ok'?(r.download_mbps<c.threshold_mbps?'Below threshold':'Within threshold'):'Test failed'];
    vals.forEach((v,i)=>{const td=document.createElement('td');td.textContent=v;if(i===5&&(r.status!=='ok'||r.download_mbps<c.threshold_mbps))td.className='bad';if(r.error)td.title=r.error;tr.append(td);});body.append(tr);
  }
  if(!s.measurements.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=6;td.className='empty';td.textContent='No tests yet. Run a speed test to begin your evidence log.';tr.append(td);body.append(tr);}
  chart(s.measurements,c);
}
async function refresh() { const s=await api('state'); current=s; if(!loaded){ initialTemplates=structuredClone(s.config.templates);fill(s.config);loaded=true;}dashboard(s); }
async function save() { if(!form.reportValidity()||!email.reportValidity()) throw Error('Check the highlighted fields before saving.'); const result=await api('settings',settings());await refresh();toast(result.message);return result; }
function busyButton(button,fn){button.addEventListener('click',async()=>{button.disabled=true;try{await fn();}catch(e){toast(e.message,true);}finally{button.disabled=false;}});}
document.querySelectorAll('.nav').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==button.dataset.view);document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b===button));}));
document.querySelectorAll('form').forEach(f=>f.addEventListener('submit',e=>e.preventDefault()));
document.querySelectorAll('.save').forEach(b=>busyButton(b,save));
document.querySelectorAll('[data-action]').forEach(b=>busyButton(b,async()=>{const r=await api(b.dataset.action,{});toast(r.message);}));
busyButton($('#test-button'),async()=>{pendingTest=true;dashboard(current);try{const r=await api('test',{});toast(r.message);}finally{setTimeout(()=>{pendingTest=false;refresh().catch(()=>{});},2500);}});
busyButton($('#schedule-toggle'),async()=>{await save();const result=await api('schedule',{enabled:!current.schedule_enabled});toast(result.message);await refresh();});
busyButton($('#save-password'),async()=>{if(!field(email,'password').value)throw Error('Enter an SMTP app password first.');await save();const result=await api('password',{password:field(email,'password').value});field(email,'password').value='';toast(result.message);});
busyButton($('#compose'),async()=>{await save();const d=current.draft;if(!d.to)throw Error('Add your provider support email before opening the draft.');location.href='mailto:'+encodeURIComponent(d.to)+'?subject='+encodeURIComponent(d.subject)+'&body='+encodeURIComponent(d.body);});
$('#reset-template').addEventListener('click',()=>{set(email,'subject',DEFAULT_SUBJECT);set(email,'body',DEFAULT_BODY);preview();toast('Default template restored. Save settings to keep it.');});
for(const f of [form,email])f.addEventListener('input',preview);
const DEFAULT_SUBJECT='Slow broadband service — {provider} — account {account_reference}';
const DEFAULT_BODY=`Dear {provider} support team,

I am writing to report consistently slow download speeds on my broadband service.

Account reference: {account_reference}
Advertised download speed: {plan_mbps} Mbps
Measured average: {average_mbps} Mbps
Monitoring period: {window_hours} hours
Successful tests: {sample_count}
Tests below {threshold_mbps} Mbps: {below_count}

The measurements were taken automatically on my Mac using Apple's networkQuality tool. Connection conditions: {connection_notes}

Please investigate the reduced speeds, confirm the minimum guaranteed download speed for my service, and provide a fault reference and an expected resolution date. Please also advise whether any service credit is available under my agreement.

I can provide the timestamped measurement report and raw results to support this request.

Kind regards,
{customer_name}
{user_email}`;
refresh().catch(e=>toast(e.message,true));
setInterval(()=>refresh().catch(()=>{}),5000);
