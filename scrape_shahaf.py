#!/usr/bin/env python3
"""איסוף מערכות כיתתיות מאתר שחף והמרתן למאגר מערכות מורים.

השימוש מיועד למידע שהאתר מציג לציבור. הסקריפט עובר על מזהי cls,
מאתר טבלאות מערכת, ושומר data/timetable.json עבור אפליקציית GitHub Pages.
"""
import json, re, time
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://beit-yerach.shahaf.site/"
CLS_MIN = 1
CLS_MAX = 160
TIMEOUT = 20
SLEEP = 0.12
OUT = Path(__file__).parent / "data" / "timetable.json"
DAYS = ["ראשון","שני","שלישי","רביעי","חמישי","שישי"]

session=requests.Session()
session.headers.update({"User-Agent":"TeacherTimetable/1.0 (+school timetable helper)"})

def clean(s): return re.sub(r"\s+"," ",(s or "").replace("\xa0"," ")).strip()

def selected_class(soup, fallback):
    sel=soup.select_one('select option[selected]')
    if sel and clean(sel.get_text()): return clean(sel.get_text())
    # לעיתים הדפדפן מסמן בחירה דרך value בלבד
    select=soup.select_one('select')
    if select:
        for o in select.find_all('option'):
            if o.get('value')==str(fallback): return clean(o.get_text())
    return f"cls-{fallback}"

def parse_room(subject_text):
    m=re.search(r"\(([^()]*)\)\s*$",subject_text)
    if not m: return subject_text.strip(), ""
    return subject_text[:m.start()].strip(), clean(m.group(1))

def plausible_time(t): return bool(re.fullmatch(r"\d{1,2}:\d{2}",t))

def extract_item(block, source_class):
    # מנסה לשמור את שורות ה-DOM ולא רק טקסט שטוח.
    lines=[clean(x) for x in block.stripped_strings if clean(x)]
    if not lines: return []
    out=[]
    # דפוס שכיח: מקצוע (חדר), שם מורה; לעיתים מספר זוגות באותו תא.
    i=0
    while i < len(lines):
        subject_line=lines[i]
        if plausible_time(subject_line) or subject_line.isdigit(): i+=1; continue
        teacher_line=lines[i+1] if i+1<len(lines) else ""
        # אם השורה הבאה נראית כמו מקצוע נוסף, נשאיר את המורה ריק ולא נבלע אותה.
        if re.search(r"\([^()]+\)$",teacher_line) and not re.search(r"[א-ת]{2,}\s+[א-ת]{2,}",teacher_line):
            teacher_line=""
        subject,room=parse_room(subject_line)
        # בחלק מהאתר שם המורה מופיע יחד עם מקצוע/חדר; ננסה לחלץ שם עברי בתחילת השורה.
        teacher=teacher_line
        if teacher:
            m=re.match(r"^([א-ת'\-]+(?:\s+[א-ת'\-]+){1,3})(?:\s+.+)?$",teacher)
            if m: teacher=clean(m.group(1))
        if subject and teacher:
            out.append({"subject":subject,"classroom":room,"teacher":teacher,"sourceClass":source_class,"group":source_class})
            i+=2
        else:
            i+=1
    return out

def parse_page(html, cls_id):
    soup=BeautifulSoup(html,'html.parser')
    text=clean(soup.get_text(' ',strip=True))
    if 'מערכת שעות' not in text: return None
    source=selected_class(soup,cls_id)
    tables=soup.find_all('table')
    if not tables: return None
    # בוחרים את הטבלה שמכילה כמה שיותר שמות ימים/שעות.
    table=max(tables,key=lambda t:sum(d in t.get_text(' ',strip=True) for d in DAYS)+len(t.find_all('tr')))
    rows=table.find_all('tr')
    records=[]; periods=[]
    # מיפוי עמודות לפי כותרת אם קיימת
    day_columns={}
    for tr in rows[:4]:
        cells=tr.find_all(['th','td'])
        for idx,c in enumerate(cells):
            tx=clean(c.get_text(' ',strip=True))
            for d in DAYS:
                if d in tx: day_columns[idx]=d
    if not day_columns:
        # באתר הנוכחי: עמודה ראשונה שעה ולאחריה ימים א-ו
        day_columns={i+1:d for i,d in enumerate(DAYS)}
    for tr in rows:
        cells=tr.find_all(['th','td'])
        if len(cells)<2: continue
        first=clean(cells[0].get_text(' ',strip=True))
        hm=re.match(r"^(\d{1,2})\b",first)
        if not hm: continue
        hour=int(hm.group(1)); times=re.findall(r"\d{1,2}:\d{2}",first)
        if len(times)>=2: periods.append({"hour":hour,"start":times[0],"end":times[1]})
        for idx,day in day_columns.items():
            if idx>=len(cells): continue
            cell=cells[idx]
            # נעדיף בלוקים פנימיים נפרדים אם קיימים.
            blocks=[x for x in cell.find_all(recursive=False) if clean(x.get_text(' ',strip=True))]
            candidates=blocks or [cell]
            seen=set()
            for b in candidates:
                for item in extract_item(b,source):
                    key=(item['teacher'],item['subject'],item['classroom'])
                    if key in seen: continue
                    seen.add(key)
                    item.update({"day":day,"hour":hour})
                    records.append(item)
    return source,records,periods

def main():
    all_records=[]; classes=[]; period_map={}
    empty_run=0
    for cls_id in range(CLS_MIN,CLS_MAX+1):
        try:
            r=session.get(BASE_URL,params={"cls":cls_id,"tab":"timetable"},timeout=TIMEOUT)
            r.raise_for_status()
            parsed=parse_page(r.text,cls_id)
            if parsed:
                source,recs,periods=parsed
                # דפים לא קיימים לעיתים מחזירים אותו תוכן; נשמור רק class name ייחודי.
                if source not in classes and recs:
                    classes.append(source); all_records.extend(recs)
                    for p in periods: period_map[p['hour']]=p
                    print(f"✓ {cls_id}: {source} — {len(recs)} רשומות")
                    empty_run=0
                else: empty_run+=1
            else: empty_run+=1
        except Exception as e:
            print(f"! {cls_id}: {e}"); empty_run+=1
        time.sleep(SLEEP)
    # הסרת כפילויות גלובלית
    uniq={}
    for r in all_records:
        k=(r['teacher'],r['day'],r['hour'],r['subject'],r.get('classroom',''),r.get('sourceClass',''))
        uniq[k]=r
    payload={
        "updatedAt":datetime.now(timezone.utc).isoformat(),
        "source":BASE_URL,
        "classes":classes,
        "periods":[period_map[k] for k in sorted(period_map)],
        "records":list(uniq.values())
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"\nנשמרו {len(payload['records'])} רשומות, {len(classes)} כיתות → {OUT}")

if __name__=='__main__': main()
