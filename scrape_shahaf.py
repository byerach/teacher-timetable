#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
איסוף מערכות כיתתיות מאתר שחף והמרתן למאגר מערכות מורים.

הסקריפט:
1. פותח את אתר מערכת השעות.
2. מנסה לזהות אוטומטית את כל מזהי הכיתות מתוך תפריט הכיתות.
3. קורא רק את מערכות הכיתות הקיימות.
4. מפריד בין:
   - מקצוע
   - מורה
   - כיתת לימוד / חדר שמופיע בסוגריים
5. שומר את הכל לקובץ:
   data/timetable.json

מיועד להרצה ידנית דרך GitHub Actions.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


# --------------------------------------------------
# הגדרות
# --------------------------------------------------

BASE_URL = "https://beit-yerach.shahaf.site/"

START_CLASS_ID = 2

TIMEOUT = 7
SLEEP = 0.08

# אם לא הצלחנו לגלות את רשימת הכיתות מהאתר,
# נשתמש בטווח הזה בלבד.
FALLBACK_MIN = 1
FALLBACK_MAX = 60

OUT = Path(__file__).parent / "data" / "timetable.json"

DAYS = [
    "ראשון",
    "שני",
    "שלישי",
    "רביעי",
    "חמישי",
    "שישי",
]


# --------------------------------------------------
# SESSION
# --------------------------------------------------

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/131.0 Safari/537.36"
    )
})


# --------------------------------------------------
# פונקציות עזר
# --------------------------------------------------

def clean(text):
    """ניקוי רווחים ותווים מיוחדים."""
    return re.sub(
        r"\s+",
        " ",
        (text or "").replace("\xa0", " ")
    ).strip()


def parse_room(subject_text):
    """
    מפריד כיתת לימוד / חדר שמופיעים בסוגריים בסוף המקצוע.

    לדוגמה:
    אנגלית (מחשבים 4)

    יהפוך ל:
    subject = אנגלית
    classroom = מחשבים 4
    """

    text = clean(subject_text)

    match = re.search(r"\(([^()]*)\)\s*$", text)

    if not match:
        return text, ""

    subject = clean(text[:match.start()])
    classroom = clean(match.group(1))

    return subject, classroom


def looks_like_teacher(text):
    """
    בדיקה גסה האם טקסט נראה כמו שם של מורה.
    """

    text = clean(text)

    if not text:
        return False

    if "(" in text or ")" in text:
        return False

    if re.fullmatch(r"\d+", text):
        return False

    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        return False

    words = text.split()

    if len(words) < 2:
        return False

    # לפחות שתי מילים בעברית
    hebrew_words = [
        w for w in words
        if re.search(r"[א-ת]", w)
    ]

    return len(hebrew_words) >= 2


def extract_teacher_name(text):
    """
    לעיתים אתר שחף מחבר:
    'סלומון שלומי אנגלית'

    ולכן ננסה לקחת את החלק שנראה כמו שם המורה.
    """

    text = clean(text)

    words = text.split()

    if len(words) <= 2:
        return text

    # שמות מורים באתר בדרך כלל 2-3 מילים.
    # אנחנו מעדיפים את שתי המילים הראשונות.
    first_two = " ".join(words[:2])

    if looks_like_teacher(first_two):
        return first_two

    return text


# --------------------------------------------------
# גילוי הכיתות באתר
# --------------------------------------------------

def discover_class_ids():
    """
    מנסה למצוא את כל מזהי cls מתוך ה-select או מתוך קישורים בדף.
    """

    print("מאתר את רשימת הכיתות באתר...")

    response = session.get(
        BASE_URL,
        params={
            "cls": START_CLASS_ID,
            "tab": "timetable",
        },
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    found = set()

    # ------------------------------------------------
    # אפשרות 1: option value בתוך select
    # ------------------------------------------------

    for option in soup.find_all("option"):

        value = clean(option.get("value", ""))

        if value.isdigit():
            found.add(int(value))

    # ------------------------------------------------
    # אפשרות 2: קישורים שיש בהם cls=
    # ------------------------------------------------

    for a in soup.find_all("a", href=True):

        href = a["href"]

        try:
            query = parse_qs(urlparse(href).query)

            if "cls" in query:

                for value in query["cls"]:

                    if value.isdigit():
                        found.add(int(value))

        except Exception:
            pass

    if found:

        ids = sorted(found)

        print(
            f"✓ נמצאו {len(ids)} מזהי כיתות "
            f"({ids[0]}–{ids[-1]})"
        )

        return ids

    # ------------------------------------------------
    # fallback
    # ------------------------------------------------

    print(
        "לא הצלחתי לקרוא את רשימת הכיתות מה-select."
    )

    print(
        f"עובר לטווח גיבוי "
        f"{FALLBACK_MIN}–{FALLBACK_MAX}."
    )

    return list(
        range(
            FALLBACK_MIN,
            FALLBACK_MAX + 1
        )
    )


# --------------------------------------------------
# שם הכיתה
# --------------------------------------------------

def get_selected_class_name(soup, cls_id):

    # selected מפורש
    selected = soup.select_one(
        "select option[selected]"
    )

    if selected:

        text = clean(
            selected.get_text(" ", strip=True)
        )

        if text:
            return text

    # חיפוש option לפי value
    for option in soup.find_all("option"):

        if clean(option.get("value")) == str(cls_id):

            text = clean(
                option.get_text(
                    " ",
                    strip=True
                )
            )

            if text:
                return text

    return f"cls-{cls_id}"


# --------------------------------------------------
# חילוץ שיעורים מתוך תא
# --------------------------------------------------

def extract_items_from_cell(cell, source_class):
    """
    חילוץ כל השיעורים מתוך תא אחד.

    האתר יכול להכיל למשל:

    אנגלית (מחשבים 4)
    סלומון שלומי
    אנגלית (ט1)
    ברקלי אביבה
    אנגלית (ט11)
    אורחוב דריה

    ולכן חשוב לא להניח שיש רק שיעור אחד בתא.
    """

    lines = [
        clean(x)
        for x in cell.stripped_strings
        if clean(x)
    ]

    if not lines:
        return []

    items = []

    i = 0

    while i < len(lines):

        line = lines[i]

        # דילוג על שעות ומספרים
        if re.fullmatch(r"\d+", line):
            i += 1
            continue

        if re.fullmatch(
            r"\d{1,2}:\d{2}",
            line
        ):
            i += 1
            continue

        # אנחנו מניחים שהשורה הנוכחית היא מקצוע
        subject, classroom = parse_room(line)

        if not subject:
            i += 1
            continue

        teacher = ""

        # השורה הבאה אמורה להיות מורה
        if i + 1 < len(lines):

            next_line = lines[i + 1]

            if looks_like_teacher(next_line):

                teacher = extract_teacher_name(
                    next_line
                )

        if teacher:

            items.append({
                "subject": subject,
                "teacher": teacher,
                "classroom": classroom,
                "sourceClass": source_class,
                "group": source_class,
            })

            i += 2

        else:

            i += 1

    return items


# --------------------------------------------------
# קריאת דף מערכת אחת
# --------------------------------------------------

def parse_page(html, cls_id):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    page_text = clean(
        soup.get_text(
            " ",
            strip=True
        )
    )

    if "מערכת שעות" not in page_text:
        return None

    source_class = get_selected_class_name(
        soup,
        cls_id
    )

    tables = soup.find_all("table")

    if not tables:
        return None

    # בוחרים את הטבלה שנראית הכי הרבה כמו מערכת שעות
    def table_score(table):

        text = clean(
            table.get_text(
                " ",
                strip=True
            )
        )

        score = 0

        for day in DAYS:

            if day in text:
                score += 10

        score += len(
            table.find_all("tr")
        )

        return score

    table = max(
        tables,
        key=table_score
    )

    rows = table.find_all("tr")

    # ------------------------------------------------
    # זיהוי עמודות ימים
    # ------------------------------------------------

    day_columns = {}

    for row in rows[:5]:

        cells = row.find_all(
            ["th", "td"]
        )

        for index, cell in enumerate(cells):

            text = clean(
                cell.get_text(
                    " ",
                    strip=True
                )
            )

            for day in DAYS:

                if day in text:
                    day_columns[index] = day

    # מבנה ברירת מחדל
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

    # ------------------------------------------------
    # מעבר על השורות
    # ------------------------------------------------

    for row in rows:

        cells = row.find_all(
            ["th", "td"]
        )

        if len(cells) < 2:
            continue

        first_cell_text = clean(
            cells[0].get_text(
                " ",
                strip=True
            )
        )

        # מספר השעה
        hour_match = re.match(
            r"^(\d{1,2})\b",
            first_cell_text
        )

        if not hour_match:
            continue

        hour = int(
            hour_match.group(1)
        )

        # שעות התחלה וסיום
        times = re.findall(
            r"\d{1,2}:\d{2}",
            first_cell_text
        )

        if len(times) >= 2:

            periods.append({
                "hour": hour,
                "start": times[0],
                "end": times[1],
            })

        # ------------------------------------------------
        # כל יום
        # ------------------------------------------------

        for column_index, day in day_columns.items():

            if column_index >= len(cells):
                continue

            cell = cells[column_index]

            items = extract_items_from_cell(
                cell,
                source_class
            )

            seen = set()

            for item in items:

                key = (
                    item["teacher"],
                    item["subject"],
                    item["classroom"],
                )

                if key in seen:
                    continue

                seen.add(key)

                item["day"] = day
                item["hour"] = hour

                records.append(item)

    return (
        source_class,
        records,
        periods,
    )


# --------------------------------------------------
# הורדת מערכת כיתה
# --------------------------------------------------

def fetch_class(cls_id):

    response = session.get(
        BASE_URL,
        params={
            "cls": cls_id,
            "tab": "timetable",
        },
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    return parse_page(
        response.text,
        cls_id
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    print()
    print("=" * 60)
    print("עדכון מערכת שעות בית ירח")
    print("=" * 60)
    print()

    class_ids = discover_class_ids()

    all_records = []

    classes = []

    period_map = {}

    seen_classes = set()

    # ------------------------------------------------
    # איסוף
    # ------------------------------------------------

    for index, cls_id in enumerate(
        class_ids,
        start=1
    ):

        print(
            f"[{index}/{len(class_ids)}] "
            f"קורא cls={cls_id}...",
            end=" "
        )

        try:

            parsed = fetch_class(cls_id)

            if not parsed:

                print("ללא מערכת")
                continue

            source_class, records, periods = parsed

            # מניעת דפים כפולים
            if source_class in seen_classes:

                print(
                    f"כפילות ({source_class})"
                )

                continue

            if not records:

                print(
                    f"{source_class} — אין שיעורים"
                )

                continue

            seen_classes.add(
                source_class
            )

            classes.append(
                source_class
            )

            all_records.extend(
                records
            )

            for period in periods:

                period_map[
                    period["hour"]
                ] = period

            print(
                f"✓ {source_class} — "
                f"{len(records)} שיעורים"
            )

        except requests.Timeout:

            print("TIMEOUT")

        except Exception as error:

            print(
                f"שגיאה: {error}"
            )

        time.sleep(SLEEP)

    # ------------------------------------------------
    # הסרת כפילויות
    # ------------------------------------------------

    unique_records = {}

    for record in all_records:

        key = (
            record["teacher"],
            record["day"],
            record["hour"],
            record["subject"],
            record.get(
                "classroom",
                ""
            ),
            record.get(
                "sourceClass",
                ""
            ),
        )

        unique_records[key] = record

    records = list(
        unique_records.values()
    )

    # ------------------------------------------------
    # מיון
    # ------------------------------------------------

    day_order = {
        day: index
        for index, day in enumerate(DAYS)
    }

    records.sort(
        key=lambda r: (
            r["teacher"],
            day_order.get(
                r["day"],
                99
            ),
            r["hour"],
            r["sourceClass"],
            r["subject"],
        )
    )

    classes.sort()

    # ------------------------------------------------
    # רשימת מורים
    # ------------------------------------------------

    teachers = sorted(
        set(
            record["teacher"]
            for record in records
            if record.get("teacher")
        )
    )

    # ------------------------------------------------
    # JSON
    # ------------------------------------------------

    payload = {

        "updatedAt": datetime.now(
            timezone.utc
        ).isoformat(),

        "source": BASE_URL,

        "classes": classes,

        "teachers": teachers,

        "periods": [
            period_map[key]
            for key in sorted(
                period_map
            )
        ],

        "records": records,
    }

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # ------------------------------------------------
    # סיכום
    # ------------------------------------------------

    print()
    print("=" * 60)

    print(
        f"✓ כיתות שנקראו: "
        f"{len(classes)}"
    )

    print(
        f"✓ מורים שנמצאו: "
        f"{len(teachers)}"
    )

    print(
        f"✓ שיעורים שנשמרו: "
        f"{len(records)}"
    )

    print(
        f"✓ הקובץ נשמר ב:"
    )

    print(OUT)

    print("=" * 60)
    print()

    if len(classes) == 0:

        raise RuntimeError(
            "לא נמצאו מערכות כיתתיות."
        )

    if len(records) == 0:

        raise RuntimeError(
            "לא נמצאו שיעורים במערכות."
        )


if __name__ == "__main__":
    main()
