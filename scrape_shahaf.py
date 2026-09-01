#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
איסוף מערכות כיתתיות מאתר שחף והמרתן למאגר מערכות מורים.

עקרונות:
- הכיתה שנבחרה בראש הדף היא קבוצת התלמידים.
- בכל תא מופיעים זוגות: מקצוע (כיתת לימוד פיזית) -> שם מורה.
- המקצוע מזוהה לפי אלמנט מודגש ב-HTML, ולא לפי "שתי מילים בעברית".
- מה שבסוגריים בסוף המקצוע נשמר כ-classroom.
- sourceClass/group היא הכיתה שאת המערכת שלה אנחנו קוראים.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

BASE_URL = "https://beit-yerach.shahaf.site/"
START_CLASS_ID = 2
TIMEOUT = 7
SLEEP = 0.08
FALLBACK_MIN = 1
FALLBACK_MAX = 70
OUT = Path(__file__).parent / "data" / "timetable.json"
DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי"]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
})


def clean(text):
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def parse_room(subject_text):
    text = clean(subject_text)
    m = re.search(r"\(([^()]*)\)\s*$", text)
    if not m:
        return text, ""
    return clean(text[:m.start()]), clean(m.group(1))


def discover_class_ids():
    print("מאתר את רשימת הכיתות באתר...")
    r = session.get(
        BASE_URL,
        params={"cls": START_CLASS_ID, "tab": "timetable"},
        timeout=TIMEOUT
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    found = set()

    for option in soup.find_all("option"):
        value = clean(option.get("value", ""))
        if value.isdigit():
            found.add(int(value))

    for a in soup.find_all("a", href=True):
        try:
            query = parse_qs(urlparse(a["href"]).query)
            for value in query.get("cls", []):
                if value.isdigit():
                    found.add(int(value))
        except Exception:
            pass

    if found:
        ids = sorted(found)
        print(f"✓ נמצאו {len(ids)} מזהי כיתות")
        return ids

    print(f"לא נמצאה רשימת כיתות; משתמש בטווח גיבוי {FALLBACK_MIN}-{FALLBACK_MAX}")
    return list(range(FALLBACK_MIN, FALLBACK_MAX + 1))


def get_selected_class_name(soup, cls_id):
    selected = soup.select_one("select option[selected]")
    if selected:
        text = clean(selected.get_text(" ", strip=True))
        if text:
            return text

    for option in soup.find_all("option"):
        if clean(option.get("value", "")) == str(cls_id):
            text = clean(option.get_text(" ", strip=True))
            if text:
                return text

    return f"cls-{cls_id}"


def is_descendant(node, ancestor):
    p = getattr(node, "parent", None)
    while p is not None:
        if p is ancestor:
            return True
        p = getattr(p, "parent", None)
    return False


def subject_nodes_in_cell(cell):
    """
    באתר שחף שמות המקצועות מודגשים.
    תומך ב-b/strong וגם באלמנטים עם style של font-weight.
    """
    candidates = []

    for tag in cell.find_all(True):
        txt = clean(tag.get_text(" ", strip=True))
        if not txt:
            continue

        is_bold_tag = tag.name in ("b", "strong")
        style = (tag.get("style") or "").lower().replace(" ", "")
        cls = " ".join(tag.get("class") or []).lower()
        is_bold_style = (
            "font-weight:bold" in style
            or "font-weight:700" in style
            or "font-weight:600" in style
            or "bold" in cls
        )

        if is_bold_tag or is_bold_style:
            # לא לקחת מיכל גדול שמכיל כמה מקצועות.
            nested_bold = tag.find(["b", "strong"])
            if nested_bold is not None and tag.name not in ("b", "strong"):
                continue
            candidates.append(tag)

    # מסירים כפילויות ונקודות שבהן אלמנט מודגש עוטף אלמנט מודגש אחר.
    result = []
    seen = set()
    for tag in candidates:
        txt = clean(tag.get_text(" ", strip=True))
        if txt in seen:
            continue
        if txt in DAYS or re.fullmatch(r"\d{1,2}", txt):
            continue
        seen.add(txt)
        result.append(tag)

    return result


def next_text_after_subject(subject_tag, cell, all_subject_tags):
    """שם המורה הוא הטקסט הראשון אחרי המקצוע ולפני המקצוע הבא."""
    next_subject_ids = {id(x) for x in all_subject_tags if x is not subject_tag}

    for node in subject_tag.next_elements:
        if isinstance(node, Tag):
            if not is_descendant(node, cell) and node is not cell:
                break
            if id(node) in next_subject_ids:
                break
            continue

        if isinstance(node, NavigableString):
            if is_descendant(node, subject_tag):
                continue
            text = clean(str(node))
            if not text:
                continue
            if re.fullmatch(r"\d{1,2}:\d{2}", text) or text.isdigit():
                continue
            return text

    return ""


def extract_items_from_cell(cell, source_class):
    subject_tags = subject_nodes_in_cell(cell)
    items = []

    for subject_tag in subject_tags:
        raw_subject = clean(subject_tag.get_text(" ", strip=True))
        teacher = next_text_after_subject(subject_tag, cell, subject_tags)
        if not teacher:
            continue

        subject, classroom = parse_room(raw_subject)
        if not subject:
            continue

        items.append({
            "subject": subject,
            "teacher": teacher,
            "classroom": classroom,
            "sourceClass": source_class,
            "group": source_class,
        })

    return items


def parse_page(html, cls_id):
    soup = BeautifulSoup(html, "html.parser")
    page_text = clean(soup.get_text(" ", strip=True))
    if "מערכת שעות" not in page_text:
        return None

    source_class = get_selected_class_name(soup, cls_id)
    tables = soup.find_all("table")
    if not tables:
        return None

    def table_score(table):
        text = clean(table.get_text(" ", strip=True))
        return sum(10 for d in DAYS if d in text) + len(table.find_all("tr"))

    table = max(tables, key=table_score)
    rows = table.find_all("tr")

    day_columns = {}
    for row in rows[:5]:
        cells = row.find_all(["th", "td"], recursive=False) or row.find_all(["th", "td"])
        for idx, cell in enumerate(cells):
            tx = clean(cell.get_text(" ", strip=True))
            for day in DAYS:
                if day in tx:
                    day_columns[idx] = day

    if not day_columns:
        day_columns = {
            1: "ראשון",
            2: "שני",
            3: "שלישי",
            4: "רביעי",
            5: "חמישי",
            6: "שישי",
        }

    records = []
    periods = []

    for row in rows:
        cells = row.find_all(["th", "td"], recursive=False) or row.find_all(["th", "td"])
        if len(cells) < 2:
            continue

        first = clean(cells[0].get_text(" ", strip=True))
        hm = re.match(r"^(\d{1,2})\b", first)
        if not hm:
            continue

        hour = int(hm.group(1))
        times = re.findall(r"\d{1,2}:\d{2}", first)
        if len(times) >= 2:
            periods.append({"hour": hour, "start": times[0], "end": times[1]})

        for idx, day in day_columns.items():
            if idx >= len(cells):
                continue

            for item in extract_items_from_cell(cells[idx], source_class):
                item["day"] = day
                item["hour"] = hour
                records.append(item)

    return source_class, records, periods


def fetch_class(cls_id):
    r = session.get(
        BASE_URL,
        params={"cls": cls_id, "tab": "timetable"},
        timeout=TIMEOUT
    )
    r.raise_for_status()
    return parse_page(r.text, cls_id)


def main():
    print("=" * 60)
    print("עדכון מערכת שעות בית ירח")
    print("=" * 60)

    class_ids = discover_class_ids()
    all_records = []
    classes = []
    period_map = {}
    seen_classes = set()

    for index, cls_id in enumerate(class_ids, 1):
        print(f"[{index}/{len(class_ids)}] cls={cls_id}...", end=" ")

        try:
            parsed = fetch_class(cls_id)

            if not parsed:
                print("ללא מערכת")
                continue

            source_class, records, periods = parsed

            if source_class in seen_classes:
                print(f"כפילות ({source_class})")
                continue

            if not records:
                print(f"{source_class} — אין שיעורים שנקראו")
                continue

            seen_classes.add(source_class)
            classes.append(source_class)
            all_records.extend(records)

            for p in periods:
                period_map[p["hour"]] = p

            print(f"✓ {source_class} — {len(records)} רשומות")

        except requests.Timeout:
            print("TIMEOUT")
        except Exception as e:
            print(f"שגיאה: {e}")

        time.sleep(SLEEP)

    # מסירים רק כפילות זהה לחלוטין.
    # כיתות מקור שונות נשמרות כדי שנוכל לאגד אותן לקבוצה אצל המורה.
    uniq = {}
    for r in all_records:
        key = (
            r["teacher"],
            r["day"],
            r["hour"],
            r["subject"],
            r.get("classroom", ""),
            r.get("sourceClass", ""),
        )
        uniq[key] = r

    records = list(uniq.values())

    day_order = {d: i for i, d in enumerate(DAYS)}
    records.sort(key=lambda r: (
        r["teacher"],
        day_order.get(r["day"], 99),
        r["hour"],
        r["subject"],
        r.get("classroom", ""),
        r.get("sourceClass", ""),
    ))

    teachers = sorted({
        r["teacher"] for r in records if r.get("teacher")
    })

    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": BASE_URL,
        "classes": sorted(classes),
        "teachers": teachers,
        "periods": [period_map[k] for k in sorted(period_map)],
        "records": records,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print()
    print("=" * 60)
    print(f"✓ כיתות: {len(classes)}")
    print(f"✓ מורים: {len(teachers)}")
    print(f"✓ רשומות: {len(records)}")
    print(f"✓ נשמר: {OUT}")
    print("=" * 60)

    if not classes or not records:
        raise RuntimeError("לא נמצאו מספיק נתוני מערכת.")


if __name__ == "__main__":
    main()
