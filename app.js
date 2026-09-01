const DAYS = ['ראשון','שני','שלישי','רביעי','חמישי','שישי'];
const DEFAULT_PERIODS = [
  {hour:0,start:'07:30',end:'08:45'}, {hour:1,start:'08:45',end:'09:30'},
  {hour:2,start:'09:35',end:'10:20'}, {hour:3,start:'10:35',end:'11:20'},
  {hour:4,start:'11:25',end:'12:10'}, {hour:5,start:'12:35',end:'13:20'},
  {hour:6,start:'13:25',end:'14:10'}, {hour:7,start:'14:30',end:'15:10'},
  {hour:8,start:'15:10',end:'15:45'}, {hour:9,start:'15:50',end:'16:50'}
];
let records=[], periods=DEFAULT_PERIODS, teachers=[], selectedTeacher='', selectedCommon=new Set();

const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

async function loadData(){
  try{
    const res=await fetch('data/timetable.json',{cache:'no-store'}); if(!res.ok) throw new Error('missing data');
    const data=await res.json(); records=Array.isArray(data.records)?data.records:[];
    if(Array.isArray(data.periods)&&data.periods.length) periods=data.periods;
    const updated=data.updatedAt?new Date(data.updatedAt).toLocaleString('he-IL'):'לא ידוע';
    $('#dataStatus').textContent=`עודכן: ${updated}`;
  }catch(e){ $('#dataStatus').textContent='לא נמצאו נתוני מערכת'; }
  teachers=[...new Set(records.map(r=>r.teacher).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'he'));
  populateTeacherSelect(); renderChecklist();
  if(teachers.length){selectedTeacher=teachers[0]; $('#teacherSelect').value=selectedTeacher; renderTeacher();}
  else renderEmptyTeacher();
}

function populateTeacherSelect(filter=''){
  const cur=$('#teacherSelect').value; const q=filter.trim();
  const list=teachers.filter(t=>!q||t.includes(q));
  $('#teacherSelect').innerHTML=list.map(t=>`<option value="${esc(t)}">${esc(t)}</option>`).join('');
  if(list.includes(cur)) $('#teacherSelect').value=cur;
}
function recordsFor(teacher,day,hour){return records.filter(r=>r.teacher===teacher&&r.day===day&&Number(r.hour)===Number(hour));}
function cellLessons(items){
  if(!items.length) return '<div class="free-cell">פנוי</div>';
  return `<div class="lesson-cell">${items.map(r=>`<div class="lesson"><div class="subject">${esc(r.subject||'שיעור')}</div>${r.group?`<div class="group">${esc(r.group)}</div>`:''}${r.classroom?`<div class="room">📍 ${esc(r.classroom)}</div>`:''}${r.sourceClass&&r.sourceClass!==r.group?`<div class="source">מערכת מקור: ${esc(r.sourceClass)}</div>`:''}</div>`).join('')}</div>`;
}
function tableHeader(){return `<thead><tr><th class="hour-col">שעה</th>${DAYS.map(d=>`<th>${d}</th>`).join('')}</tr></thead>`;}
function renderTeacher(){
  const t=selectedTeacher; $('#teacherName').textContent=t||'—';
  const lessonSlots=new Set(records.filter(r=>r.teacher===t).map(r=>`${r.day}|${r.hour}`));
  $('#lessonCount').textContent=lessonSlots.size;
  $('#freeCount').textContent=Math.max(0,periods.length*DAYS.length-lessonSlots.size);
  $('#teacherTable').innerHTML=tableHeader()+`<tbody>${periods.map(p=>`<tr><td class="hour-cell"><strong>${p.hour}</strong>${esc(p.start)}–${esc(p.end)}</td>${DAYS.map(d=>`<td>${cellLessons(recordsFor(t,d,p.hour))}</td>`).join('')}</tr>`).join('')}</tbody>`;
}
function renderEmptyTeacher(){ $('#teacherName').textContent='אין נתונים'; $('#teacherTable').innerHTML=tableHeader()+`<tbody><tr><td colspan="7" style="padding:30px;text-align:center">יש להריץ את סקריפט איסוף הנתונים.</td></tr></tbody>`; }

function renderChecklist(filter=''){
  const q=filter.trim(); const list=teachers.filter(t=>!q||t.includes(q));
  $('#teacherChecklist').innerHTML=list.map(t=>`<label class="teacher-check"><input type="checkbox" value="${esc(t)}" ${selectedCommon.has(t)?'checked':''}><span>${esc(t)}</span></label>`).join('');
  $$('#teacherChecklist input').forEach(cb=>cb.addEventListener('change',()=>{cb.checked?selectedCommon.add(cb.value):selectedCommon.delete(cb.value); renderCommon(); renderChecklist($('#commonSearch').value);}));
}
function slotState(day,hour){
  const names=[...selectedCommon]; const people=names.map(t=>({teacher:t,items:recordsFor(t,day,hour)})); const free=people.filter(p=>p.items.length===0).length;
  return {people,free,total:names.length};
}
function renderCommon(){
  const names=[...selectedCommon]; $('#selectedCount').textContent=names.length;
  $('#selectedChips').innerHTML=names.map(t=>`<span class="chip">${esc(t)}</span>`).join('');
  let allFree=0,best=null;
  const rows=periods.map(p=>`<tr><td class="hour-cell"><strong>${p.hour}</strong>${esc(p.start)}–${esc(p.end)}</td>${DAYS.map(d=>{
    const s=slotState(d,p.hour); if(s.total&&s.free===s.total) allFree++;
    if(s.total && (!best||s.free/best.total>best.free/best.total)) best={...s,day:d,hour:p.hour};
    const cls=!s.total?'none':s.free===s.total?'all':s.free/s.total>=.7?'most':'low';
    const label=!s.total?'בחרו מורים':`${s.free}/${s.total} פנויים`;
    return `<td><button type="button" class="availability ${cls}" data-day="${esc(d)}" data-hour="${p.hour}" ${!s.total?'disabled':''}><strong>${label}</strong><span>${s.free===s.total&&s.total?'כולם פנויים':s.total?'לחצו לפרטים':''}</span></button></td>`;
  }).join('')}</tr>`).join('');
  $('#allFreeCount').textContent=allFree;
  $('#bestMatch').textContent=best?`${best.free}/${best.total}`:'—';
  $('#commonTable').innerHTML=tableHeader()+`<tbody>${rows}</tbody>`;
  $$('.availability:not(:disabled)').forEach(b=>b.addEventListener('click',()=>showSlot(b.dataset.day,Number(b.dataset.hour))));
  if(!names.length) $('#slotDetails').classList.add('hidden');
}
function showSlot(day,hour){
  const s=slotState(day,hour), p=periods.find(x=>Number(x.hour)===hour);
  $('#slotDetails').innerHTML=`<h3>${esc(day)} · שעה ${hour} ${p?`(${esc(p.start)}–${esc(p.end)})`:''}</h3><div class="detail-grid">${s.people.map(x=>x.items.length?`<div class="person-detail busy"><strong>❌ ${esc(x.teacher)}</strong>${x.items.map(i=>`<small>${esc(i.subject)}${i.group?` · ${esc(i.group)}`:''}${i.classroom?` · 📍 ${esc(i.classroom)}`:''}</small>`).join('<br>')}</div>`:`<div class="person-detail free"><strong>✅ ${esc(x.teacher)}</strong><small>פנוי/ה</small></div>`).join('')}</div>`;
  $('#slotDetails').classList.remove('hidden');
}

$$('.tab').forEach(b=>b.addEventListener('click',()=>{$$('.tab').forEach(x=>x.classList.remove('active')); b.classList.add('active'); $$('.view').forEach(x=>x.classList.remove('active')); $(`#${b.dataset.tab}View`).classList.add('active');}));
$('#teacherSearch').addEventListener('input',e=>populateTeacherSelect(e.target.value));
$('#teacherSelect').addEventListener('change',e=>{selectedTeacher=e.target.value;renderTeacher();});
$('#commonSearch').addEventListener('input',e=>renderChecklist(e.target.value));
$('#clearTeachers').addEventListener('click',()=>{selectedCommon.clear();renderChecklist($('#commonSearch').value);renderCommon();});
loadData().then(renderCommon);
