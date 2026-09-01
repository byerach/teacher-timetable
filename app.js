// הוסרו יום שישי (תמיד ריק בפועל) ושעות 0/9/10
// (שעות שאין להן משמעות לימודית אמיתית).
const DAYS = ['ראשון','שני','שלישי','רביעי','חמישי'];
const VALID_HOURS = new Set([1,2,3,4,5,6,7,8]);

// מערכת הצבעים בונה עבור כל מורה, בכל רינדור, מפה
// דינמית של צבעים - כך שיש תמיד מספיק צבעים שונים
// ומרוחקים זה מזה על גלגל הצבעים (לא פלטה קבועה
// שחוזרת על עצמה כשיש הרבה קבוצות).
//
// מפתח הצביעה הוא "מקצוע + קבוצת תלמידים" (ולא כולל
// את החדר הפיזי בכוונה) - כי אותו שיעור בדיוק יכול
// להתקיים בחדרים שונים בימים שונים, וזה עדיין אותו
// שיעור מבחינת המורה. לעומת זאת אם המקצוע שונה, או
// שהתלמידים שונים, זה חייב לקבל צבע אחר.
function lessonColorKey(r){
  const subject = r.subject || 'שיעור';
  const group = r.groups?.length ? groupText(r.groups) : '';

  return group ? `${subject}‖${group}` : '';
}

function buildTeacherColorMap(teacherRecords){
  const seen = new Map();

  for(const r of teacherRecords){
    const key = lessonColorKey(r);

    if(!key || seen.has(key)) continue;

    seen.set(key,{
      subject: r.subject || 'שיעור',
      group: groupText(r.groups)
    });
  }

  const combos = [...seen.entries()].sort((a,b)=>
    naturalSort(a[1].group, b[1].group) ||
    naturalSort(a[1].subject, b[1].subject)
  );

  const n = combos.length || 1;
  const colorMap = new Map();

  combos.forEach(([key],i)=>{
    const hue = Math.round((360 / n) * i);

    colorMap.set(key,{
      bg: `hsl(${hue}, 65%, 90%)`,
      text: `hsl(${hue}, 70%, 28%)`
    });
  });

  return {colorMap, combos};
}

const DEFAULT_PERIODS = [
  {hour:1,start:'08:45',end:'09:30'},
  {hour:2,start:'09:35',end:'10:20'},
  {hour:3,start:'10:35',end:'11:20'},
  {hour:4,start:'11:25',end:'12:10'},
  {hour:5,start:'12:35',end:'13:20'},
  {hour:6,start:'13:25',end:'14:10'},
  {hour:7,start:'14:30',end:'15:10'},
  {hour:8,start:'15:10',end:'15:45'}
];

let rawRecords = [];
let records = [];
let periods = DEFAULT_PERIODS;
let teachers = [];
let selectedTeacher = '';
let selectedCommon = new Set();

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

const esc = s => String(s ?? '').replace(
  /[&<>'"]/g,
  c => ({
    '&':'&amp;',
    '<':'&lt;',
    '>':'&gt;',
    "'":'&#39;',
    '"':'&quot;'
  }[c])
);

function naturalSort(a,b){
  return String(a).localeCompare(String(b),'he',{numeric:true,sensitivity:'base'});
}

/*
  מאחד אותו שיעור שמופיע בכמה מערכות כיתתיות.

  לדוגמה:
  דה בוק ליאור | רביעי 3 | אנגלית | חדר ט3 | מקור ט2
  דה בוק ליאור | רביעי 3 | אנגלית | חדר ט3 | מקור ט3
  דה בוק ליאור | רביעי 3 | אנגלית | חדר ט3 | מקור ט4

  יהפוך לשיעור אחד עם groups = [ט2,ט3,ט4].
*/
function mergeTeacherLessons(input){
  const map = new Map();

  for(const r of input){
    if(!r.teacher || !r.day || r.hour === undefined) continue;

    const key = [
      r.teacher,
      r.day,
      Number(r.hour),
      r.subject || '',
      r.classroom || ''
    ].join('|');

    if(!map.has(key)){
      map.set(key,{
        teacher:r.teacher,
        day:r.day,
        hour:Number(r.hour),
        subject:r.subject || 'שיעור',
        classroom:r.classroom || '',
        groups:[],
        sourceClasses:[]
      });
    }

    const item = map.get(key);
    const source = r.sourceClass || r.group || '';

    if(source && !item.groups.includes(source)){
      item.groups.push(source);
    }

    if(source && !item.sourceClasses.includes(source)){
      item.sourceClasses.push(source);
    }
  }

  const merged = [...map.values()];

  for(const r of merged){
    r.groups.sort(naturalSort);
    r.sourceClasses.sort(naturalSort);
  }

  return merged;
}

async function loadData(){
  try{
    const res = await fetch('data/timetable.json',{cache:'no-store'});
    if(!res.ok) throw new Error('missing data');

    const data = await res.json();

    const allRecords = Array.isArray(data.records) ? data.records : [];

    // מסננים החוצה לגמרי יום שישי ושעות 0/9/10 -
    // אין להם משמעות לימודית, כך שגם הספירות (שיעורים
    // השבוע / שעות פנויות וכו') לא ייספרו אותם בטעות.
    rawRecords = allRecords.filter(
      r => DAYS.includes(r.day) && VALID_HOURS.has(Number(r.hour))
    );

    records = mergeTeacherLessons(rawRecords);

    if(Array.isArray(data.periods) && data.periods.length){
      periods = data.periods.filter(
        p => VALID_HOURS.has(Number(p.hour))
      );
    }

    const updated = data.updatedAt
      ? new Date(data.updatedAt).toLocaleString('he-IL')
      : 'לא ידוע';

    $('#dataStatus').textContent = `עודכן: ${updated}`;
  }catch(e){
    $('#dataStatus').textContent = 'לא נמצאו נתוני מערכת';
    rawRecords = [];
    records = [];
  }

  teachers = [...new Set(
    records.map(r=>r.teacher).filter(Boolean)
  )].sort(naturalSort);

  renderChecklist();

  if(teachers.length){
    renderNoSelection();
  }else{
    renderEmptyTeacher();
  }
}

let teacherActiveIndex = -1;

function teacherOptionsFiltered(filter=''){
  const q = filter.trim();
  return teachers.filter(t => !q || t.includes(q));
}

function renderTeacherOptions(filter=''){
  const list = teacherOptionsFiltered(filter);

  teacherActiveIndex = -1;

  const box = $('#teacherOptions');

  if(!list.length){
    box.innerHTML = `<div class="combobox-empty">לא נמצאו מורים</div>`;
    return;
  }

  box.innerHTML = list.map(t=>`
    <div
      class="combobox-option${t === selectedTeacher ? ' active' : ''}"
      role="option"
      data-teacher="${esc(t)}"
    >${esc(t)}</div>
  `).join('');
}

function openTeacherOptions(){
  renderTeacherOptions($('#teacherSearch').value);
  $('#teacherOptions').classList.remove('hidden');
  $('#teacherSearch').setAttribute('aria-expanded','true');
}

function closeTeacherOptions(){
  $('#teacherOptions').classList.add('hidden');
  $('#teacherSearch').setAttribute('aria-expanded','false');
}

function moveTeacherActive(delta){
  const options = $$('#teacherOptions .combobox-option');

  if(!options.length) return;

  teacherActiveIndex = (teacherActiveIndex + delta + options.length) % options.length;

  options.forEach((el,i)=>{
    el.classList.toggle('active', i === teacherActiveIndex);
  });

  options[teacherActiveIndex].scrollIntoView({block:'nearest'});
}

function pickTeacher(name){
  if(!name) return;

  selectedTeacher = name;
  closeTeacherOptions();
  renderTeacher();

  // מנקים את החיפוש אחרי בחירה, כדי שאפשר יהיה
  // מיד להקליד ולבחור מורה אחר בלי למחוק ידנית.
  $('#teacherSearch').value = '';
  $('#teacherSearch').focus();
}

function recordsFor(teacher,day,hour){
  return records.filter(
    r =>
      r.teacher === teacher &&
      r.day === day &&
      Number(r.hour) === Number(hour)
  );
}

function groupText(groups){
  if(!groups || !groups.length) return '';
  return groups.join(', ');
}

function cellLessons(items, colorMode, colorMap){
  if(!items.length){
    return '<div class="free-cell">פנוי</div>';
  }

  return `
    <div class="lesson-cell">
      ${items.map(r=>{
        const subject = r.subject || 'שיעור';
        const key = lessonColorKey(r);
        const c = (colorMode && key) ? colorMap.get(key) : null;

        const style = c
          ? `style="background:${c.bg};border-color:${c.bg};color:${c.text}"`
          : '';

        return `
        <div class="lesson" ${style}>
          <div class="subject">${esc(subject)}</div>

          ${r.groups?.length
            ? `<div class="group">תלמידים מ: ${esc(groupText(r.groups))}</div>`
            : ''
          }

          ${r.classroom
            ? `<div class="room">📍 ${esc(r.classroom)}</div>`
            : ''
          }
        </div>
        `;
      }).join('')}
    </div>
  `;
}

function tableHeader(){
  return `
    <thead>
      <tr>
        <th class="hour-col">שעה</th>
        ${DAYS.map(d=>`<th>${d}</th>`).join('')}
      </tr>
    </thead>
  `;
}

function renderTeacher(){
  const t = selectedTeacher;
  const colorMode = $('#colorToggle').checked;

  $('#teacherName').textContent = t || '—';

  const teacherRecords = records.filter(
    r => r.teacher === t
  );

  const lessonSlots = new Set(
    teacherRecords.map(r=>`${r.day}|${r.hour}`)
  );

  $('#lessonCount').textContent = lessonSlots.size;

  $('#freeCount').textContent = Math.max(
    0,
    periods.length * DAYS.length - lessonSlots.size
  );

  const {colorMap, combos} = buildTeacherColorMap(teacherRecords);

  renderColorLegend(colorMode, combos, colorMap);

  $('#teacherTable').innerHTML =
    tableHeader() +
    `<tbody>
      ${periods.map(p=>`
        <tr>
          <td class="hour-cell">
            <strong>${p.hour}</strong>
            ${esc(p.start)}–${esc(p.end)}
          </td>

          ${DAYS.map(d=>`
            <td class="teacher-slot" data-day="${esc(d)}" data-hour="${p.hour}">${cellLessons(recordsFor(t,d,p.hour), colorMode, colorMap)}</td>
          `).join('')}
        </tr>
      `).join('')}
    </tbody>`;

  $$('#teacherTable td.teacher-slot').forEach(td=>{
    td.addEventListener('click',()=>{
      showTeacherSlot(t, td.dataset.day, Number(td.dataset.hour));
    });
  });
}

function renderColorLegend(colorMode, combos, colorMap){
  const box = $('#colorLegend');

  if(!colorMode){
    box.innerHTML = '';
    box.classList.add('hidden');
    return;
  }

  box.classList.remove('hidden');

  if(!combos.length){
    box.innerHTML = `
      <span class="legend-empty">אין מידע על קבוצות תלמידים במערכת הזו.</span>
    `;
    return;
  }

  box.innerHTML = combos.map(([key, info])=>{
    const c = colorMap.get(key);

    return `
      <span
        class="legend-chip"
        style="background:${c.bg};color:${c.text};border-color:${c.bg}"
      >${esc(info.subject)} · תלמידים מ: ${esc(info.group)}</span>
    `;
  }).join('');
}

function renderNoSelection(){
  $('#teacherName').textContent = '—';
  $('#lessonCount').textContent = '0';
  $('#freeCount').textContent = '0';

  $('#colorLegend').innerHTML = '';
  $('#colorLegend').classList.add('hidden');

  $('#teacherTable').innerHTML =
    tableHeader() +
    `<tbody>
      <tr>
        <td colspan="7" style="padding:40px;text-align:center;color:var(--muted)">
          בחרו מורה למעלה כדי לראות את המערכת השבועית שלו/ה.
        </td>
      </tr>
    </tbody>`;
}

function renderEmptyTeacher(){
  $('#teacherName').textContent = 'אין נתונים';

  $('#colorLegend').innerHTML = '';
  $('#colorLegend').classList.add('hidden');

  $('#teacherTable').innerHTML =
    tableHeader() +
    `<tbody>
      <tr>
        <td colspan="7" style="padding:30px;text-align:center">
          יש להריץ את עדכון מערכת השעות.
        </td>
      </tr>
    </tbody>`;
}

function renderChecklist(filter=''){
  const q = filter.trim();

  const list = teachers.filter(
    t => !q || t.includes(q)
  );

  $('#teacherChecklist').innerHTML = list.map(t=>`
    <label class="teacher-check">
      <input
        type="checkbox"
        value="${esc(t)}"
        ${selectedCommon.has(t) ? 'checked' : ''}
      >
      <span>${esc(t)}</span>
    </label>
  `).join('');

  $$('#teacherChecklist input').forEach(cb=>{
    cb.addEventListener('change',()=>{
      if(cb.checked){
        selectedCommon.add(cb.value);
      }else{
        selectedCommon.delete(cb.value);
      }

      renderCommon();

      // מנקים את החיפוש אחרי סימון, כדי שאפשר יהיה
      // מיד לחפש ולסמן את המורה הבא בלי למחוק ידנית.
      $('#commonSearch').value = '';
      renderChecklist('');
      $('#commonSearch').focus();
    });
  });
}

function slotState(day,hour){
  const names = [...selectedCommon];

  const people = names.map(t=>({
    teacher:t,
    items:recordsFor(t,day,hour)
  }));

  const free = people.filter(
    p => p.items.length === 0
  ).length;

  return {
    people,
    free,
    total:names.length
  };
}

function renderCommon(){
  const names = [...selectedCommon];

  $('#selectedCount').textContent = names.length;

  $('#selectedChips').innerHTML = names
    .map(t=>`<span class="chip">${esc(t)}</span>`)
    .join('');

  let allFree = 0;
  let best = null;

  const rows = periods.map(p=>`
    <tr>
      <td class="hour-cell">
        <strong>${p.hour}</strong>
        ${esc(p.start)}–${esc(p.end)}
      </td>

      ${DAYS.map(d=>{
        const s = slotState(d,p.hour);

        if(s.total && s.free === s.total){
          allFree++;
        }

        if(
          s.total &&
          (!best || s.free / s.total > best.free / best.total)
        ){
          best = {
            ...s,
            day:d,
            hour:p.hour
          };
        }

        const cls =
          !s.total ? 'none' :
          s.free === s.total ? 'all' :
          s.free / s.total >= .7 ? 'most' :
          'low';

        const label = !s.total
          ? 'בחרו מורים'
          : `${s.free}/${s.total} פנויים`;

        return `
          <td>
            <button
              type="button"
              class="availability ${cls}"
              data-day="${esc(d)}"
              data-hour="${p.hour}"
              title="${s.total ? 'לחצו לפרטים' : ''}"
              ${!s.total ? 'disabled' : ''}
            >
              <strong>${label}</strong>
            </button>
          </td>
        `;
      }).join('')}
    </tr>
  `).join('');

  $('#allFreeCount').textContent = allFree;

  $('#bestMatch').textContent = best
    ? `${best.free}/${best.total}`
    : '—';

  $('#commonTable').innerHTML =
    tableHeader() +
    `<tbody>${rows}</tbody>`;

  $$('.availability:not(:disabled)').forEach(b=>{
    b.addEventListener('click',()=>{
      showSlot(
        b.dataset.day,
        Number(b.dataset.hour)
      );
    });
  });

  if(!names.length){
    $('#slotModal').classList.add('hidden');
  }
}

function showTeacherSlot(teacher, day, hour){
  const items = recordsFor(teacher, day, hour);

  const p = periods.find(
    x => Number(x.hour) === Number(hour)
  );

  $('#slotDetails').innerHTML = `
    <h3>
      ${esc(day)} · שעה ${hour}
      ${p ? `(${esc(p.start)}–${esc(p.end)})` : ''}
    </h3>

    ${!items.length
      ? `
        <div class="person-detail free">
          <strong>✅ ${esc(teacher)}</strong>
          <small>פנוי/ה</small>
        </div>
      `
      : items.map(i=>`
          <div class="detail-lesson">
            <div class="subject">${esc(i.subject || 'שיעור')}</div>

            ${i.groups?.length
              ? `<div class="group">תלמידים מ: ${esc(groupText(i.groups))}</div>`
              : ''
            }

            ${i.classroom
              ? `<div class="room">📍 ${esc(i.classroom)}</div>`
              : ''
            }
          </div>
        `).join('')
    }
  `;

  $('#slotModal').classList.remove('hidden');
}

function showSlot(day,hour){
  const s = slotState(day,hour);

  const p = periods.find(
    x => Number(x.hour) === Number(hour)
  );

  $('#slotDetails').innerHTML = `
    <h3>
      ${esc(day)} · שעה ${hour}
      ${p ? `(${esc(p.start)}–${esc(p.end)})` : ''}
    </h3>

    <div class="detail-grid">
      ${s.people.map(x=>{
        if(!x.items.length){
          return `
            <div class="person-detail free">
              <strong>✅ ${esc(x.teacher)}</strong>
              <small>פנוי/ה</small>
            </div>
          `;
        }

        return `
          <div class="person-detail busy">
            <strong>❌ ${esc(x.teacher)}</strong>

            ${x.items.map(i=>`
              <small>
                ${esc(i.subject)}
                ${i.groups?.length
                  ? ` · תלמידים מ: ${esc(groupText(i.groups))}`
                  : ''
                }
                ${i.classroom
                  ? ` · 📍 ${esc(i.classroom)}`
                  : ''
                }
              </small>
            `).join('<br>')}
          </div>
        `;
      }).join('')}
    </div>
  `;

  $('#slotModal').classList.remove('hidden');
}

function closeSlotModal(){
  $('#slotModal').classList.add('hidden');
}

$('#closeSlotModal').addEventListener('click', closeSlotModal);

$('#slotModal').addEventListener('click', e=>{
  if(e.target.id === 'slotModal') closeSlotModal();
});

document.addEventListener('keydown', e=>{
  if(e.key === 'Escape') closeSlotModal();
});

$$('.tab').forEach(b=>{
  b.addEventListener('click',()=>{
    $$('.tab').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');

    $$('.view').forEach(x=>x.classList.remove('active'));
    $(`#${b.dataset.tab}View`).classList.add('active');
  });
});

$('#teacherSearch').addEventListener('input', ()=>{
  openTeacherOptions();
});

$('#teacherSearch').addEventListener('focus', ()=>{
  openTeacherOptions();
});

$('#teacherSearch').addEventListener('keydown', e=>{
  const isOpen = !$('#teacherOptions').classList.contains('hidden');

  if(e.key === 'ArrowDown'){
    e.preventDefault();
    if(!isOpen){
      openTeacherOptions();
    }else{
      moveTeacherActive(1);
    }
  }else if(e.key === 'ArrowUp'){
    e.preventDefault();
    if(isOpen) moveTeacherActive(-1);
  }else if(e.key === 'Enter'){
    e.preventDefault();

    const options = $$('#teacherOptions .combobox-option');

    if(teacherActiveIndex >= 0 && options[teacherActiveIndex]){
      pickTeacher(options[teacherActiveIndex].dataset.teacher);
    }else{
      const list = teacherOptionsFiltered($('#teacherSearch').value);
      if(list.length === 1) pickTeacher(list[0]);
    }
  }else if(e.key === 'Escape'){
    closeTeacherOptions();
  }
});

$('#teacherOptions').addEventListener('click', e=>{
  const opt = e.target.closest('.combobox-option');
  if(!opt) return;
  pickTeacher(opt.dataset.teacher);
});

document.addEventListener('click', e=>{
  if(!$('#teacherCombobox').contains(e.target)){
    closeTeacherOptions();
  }
});

$('#colorToggle').addEventListener('change', ()=>{
  if(selectedTeacher) renderTeacher();
});

$('#commonSearch').addEventListener('input',e=>{
  renderChecklist(e.target.value);
});

$('#clearTeachers').addEventListener('click',()=>{
  selectedCommon.clear();
  renderChecklist($('#commonSearch').value);
  renderCommon();
});

loadData().then(renderCommon);
