#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
איסוף מערכות כיתתיות מאתר שחף והמרתן למאגר מערכות מורים.

מבנה אתר שחף:
- הכיתה שנבחרה בראש הדף = קבוצת התלמידים (sourceClass / group).
- בכל תא יש שיעור אחד או יותר.
- שם המקצוע מודגש.
- מיד אחרי המקצוע עשויה להופיע כיתת לימוד פיזית בסוגריים.
- אחרי הסוגריים (או מיד אחרי המקצוע כשאין סוגריים) מופיע שם המורה.

דוגמה:
    אנגלית (ט3)
    דה בוק ליאור

פירוש:
    subject = אנגלית
    classroom = ט3
    teacher = דה בוק ליאור
    group = הכיתה שאת המערכת שלה קוראים, למשל ט2
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

DAYS = [
    "ראשון",
    "שני",
    "שלישי",
    "רביעי",
    "חמישי",
    "שישי",
]


session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/131.0 Safari/537.36"
    )
})


def clean(text):
    return re.sub(
        r"\s+",
        " ",
        (text or "").replace("\xa0", " ")
    ).strip()


def discover_class_ids():
    """
    גילוי כל מזהי הכיתות מתוך select / קישורים באתר.
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

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    found = set()

    # option value
    for option in soup.find_all("option"):
        value = clean(
            option.get("value", "")
        )

        if value.isdigit():
            found.add(
                int(value)
            )

    # קישורים עם cls=
    for a in soup.find_all(
        "a",
        href=True
    ):
        try:
            query = parse_qs(
                urlparse(a["href"]).query
            )

            for value in query.get(
                "cls",
                []
            ):
                if value.isdigit():
                    found.add(
                        int(value)
                    )

        except Exception:
            pass

    if found:
        ids = sorted(found)

        print(
            f"✓ נמצאו {len(ids)} מזהי כיתות"
        )

        return ids

    print(
        f"לא נמצאה רשימת כיתות; "
        f"משתמש בטווח {FALLBACK_MIN}-{FALLBACK_MAX}"
    )

    return list(
        range(
            FALLBACK_MIN,
            FALLBACK_MAX + 1
        )
    )


def get_selected_class_name(
    soup,
    cls_id
):
    """
    שם הכיתה שהמערכת שלה מוצגת כרגע.
    """

    selected = soup.select_one(
        "select option[selected]"
    )

    if selected:
        text = clean(
            selected.get_text(
                " ",
                strip=True
            )
        )

        if text:
            return text

    for option in soup.find_all(
        "option"
    ):
        if clean(
            option.get(
                "value",
                ""
            )
        ) == str(cls_id):

            text = clean(
                option.get_text(
                    " ",
                    strip=True
                )
            )

            if text:
                return text

    return f"cls-{cls_id}"


def is_inside(
    node,
    ancestor
):
    parent = getattr(
        node,
        "parent",
        None
    )

    while parent is not None:

        if parent is ancestor:
            return True

        parent = getattr(
            parent,
            "parent",
            None
        )

    return False


def is_subject_tag(tag):
    """
    באתר שם המקצוע מודגש.
    """

    if not isinstance(
        tag,
        Tag
    ):
        return False

    if tag.name in (
        "b",
        "strong"
    ):
        return True

    style = (
        tag.get("style")
        or ""
    ).lower().replace(
        " ",
        ""
    )

    classes = " ".join(
        tag.get("class")
        or []
    ).lower()

    return (
        "font-weight:bold" in style
        or "font-weight:700" in style
        or "font-weight:600" in style
        or "font-weight:bold" in classes
    )


def subject_tags_in_cell(cell):
    """
    החזרת תגיות המקצוע המודגשות בלבד.
    """

    result = []

    for tag in cell.find_all(True):

        if not is_subject_tag(tag):
            continue

        text = clean(
            tag.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        # לא ימים / מספרי שעות
        if text in DAYS:
            continue

        if re.fullmatch(
            r"\d{1,2}",
            text
        ):
            continue

        # אם תג גדול עוטף תג bold אמיתי,
        # משתמשים בילד המודגש ולא במעטפת.
        nested = [
            x for x in tag.find_all(
                ["b", "strong"]
            )
            if x is not tag
        ]

        if nested and tag.name not in (
            "b",
            "strong"
        ):
            continue

        result.append(tag)

    # הסרת כפילויות DOM
    unique = []

    seen_ids = set()

    for tag in result:

        if id(tag) in seen_ids:
            continue

        seen_ids.add(
            id(tag)
        )

        unique.append(tag)

    return unique


def text_after_subject(
    subject_tag,
    cell,
    subject_tags
):
    """
    מחזיר את קטעי הטקסט אחרי המקצוע ועד המקצוע המודגש הבא.

    לדוגמה:
        subject_tag = אנגלית

    chunks:
        ["(ט3)", "דה בוק ליאור"]
    """

    other_subjects = {
        id(x)
        for x in subject_tags
        if x is not subject_tag
    }

    chunks = []

    for node in subject_tag.next_elements:

        # יצאנו מהתא
        if not is_inside(
            node,
            cell
        ) and node is not cell:
            break

        if isinstance(
            node,
            Tag
        ):

            # הגענו למקצוע הבא
            if id(node) in other_subjects:
                break

            continue

        if not isinstance(
            node,
            NavigableString
        ):
            continue

        # לא לקחת את הטקסט שבתוך תג המקצוע עצמו
        if is_inside(
            node,
            subject_tag
        ):
            continue

        text = clean(
            str(node)
        )

        if not text:
            continue

        # מניעת כפילויות טקסט רצופות
        if (
            chunks
            and chunks[-1] == text
        ):
            continue

        chunks.append(text)

    return chunks


def parse_lesson_after_subject(
    subject_tag,
    cell,
    subject_tags
):
    """
    פענוח שיעור בודד:

    מקצוע מודגש
    (חדר/כיתה) - אופציונלי
    שם המורה
    """

    subject = clean(
        subject_tag.get_text(
            " ",
            strip=True
        )
    )

    chunks = text_after_subject(
        subject_tag,
        cell,
        subject_tags
    )

    classroom = ""
    teacher = ""

    for text in chunks:

        # טקסט שהוא רק סוגריים = כיתת לימוד
        room_match = re.fullmatch(
            r"\(([^()]*)\)",
            text
        )

        if (
            room_match
            and not classroom
        ):
            classroom = clean(
                room_match.group(1)
            )
            continue

        # לפעמים ה-HTML מפצל את הסוגריים
        # אבל הטקסט עדיין מתחיל/נגמר בהם.
        if (
            text.startswith("(")
            and text.endswith(")")
            and not classroom
        ):
            classroom = clean(
                text[1:-1]
            )
            continue

        # הדבר הראשון שאינו סוגריים הוא שם המורה
        teacher = text
        break

    if not teacher:
        return None

    return {
        "subject": subject,
        "teacher": teacher,
        "classroom": classroom,
    }


def extract_items_from_cell(
    cell,
    source_class
):
    """
    חילוץ כל זוגות המקצוע/מורה מתוך תא.
    """

    subjects = subject_tags_in_cell(
        cell
    )

    items = []

    for subject_tag in subjects:

        lesson = parse_lesson_after_subject(
            subject_tag,
            cell,
            subjects
        )

        if not lesson:
            continue

        items.append({
            "subject": lesson["subject"],
            "teacher": lesson["teacher"],
            "classroom": lesson["classroom"],

            # הכיתה שאת המערכת שלה אנו קוראים
            "sourceClass": source_class,
            "group": source_class,
        })

    return items


def parse_page(
    html,
    cls_id
):
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

    tables = soup.find_all(
        "table"
    )

    if not tables:
        return None

    def table_score(table):

        text = clean(
            table.get_text(
                " ",
                strip=True
            )
        )

        return (
            sum(
                10
                for day in DAYS
                if day in text
            )
            + len(
                table.find_all(
                    "tr"
                )
            )
        )

    table = max(
        tables,
        key=table_score
    )

    rows = table.find_all(
        "tr"
    )

    # מיפוי עמודות ימים
    day_columns = {}

    for row in rows[:5]:

        cells = row.find_all(
            ["th", "td"],
            recursive=False
        )

        if not cells:
            cells = row.find_all(
                ["th", "td"]
            )

        for index, cell in enumerate(
            cells
        ):

            text = clean(
                cell.get_text(
                    " ",
                    strip=True
                )
            )

            for day in DAYS:

                if day in text:
                    day_columns[
                        index
                    ] = day

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

        cells = row.find_all(
            ["th", "td"],
            recursive=False
        )

        if not cells:
            cells = row.find_all(
                ["th", "td"]
            )

        if len(cells) < 2:
            continue

        first_text = clean(
            cells[0].get_text(
                " ",
                strip=True
            )
        )

        hour_match = re.match(
            r"^(\d{1,2})\b",
            first_text
        )

        if not hour_match:
            continue

        hour = int(
            hour_match.group(1)
        )

        times = re.findall(
            r"\d{1,2}:\d{2}",
            first_text
        )

        if len(times) >= 2:
            periods.append({
                "hour": hour,
                "start": times[0],
                "end": times[1],
            })

        for column_index, day in day_columns.items():

            if column_index >= len(
                cells
            ):
                continue

            cell = cells[
                column_index
            ]

            lessons = extract_items_from_cell(
                cell,
                source_class
            )

            seen = set()

            for lesson in lessons:

                key = (
                    lesson["subject"],
                    lesson["teacher"],
                    lesson["classroom"],
                )

                if key in seen:
                    continue

                seen.add(key)

                lesson["day"] = day
                lesson["hour"] = hour

                records.append(
                    lesson
                )

    return (
        source_class,
        records,
        periods,
    )


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

    for index, cls_id in enumerate(
        class_ids,
        start=1
    ):

        print(
            f"[{index}/{len(class_ids)}] "
            f"cls={cls_id}...",
            end=" "
        )

        try:

            parsed = fetch_class(
                cls_id
            )

            if not parsed:
                print("ללא מערכת")
                continue

            source_class, records, periods = parsed

            if source_class in seen_classes:
                print(
                    f"כפילות ({source_class})"
                )
                continue

            if not records:
                print(
                    f"{source_class} — "
                    f"אין שיעורים"
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
                f"{len(records)} רשומות"
            )

        except requests.Timeout:
            print("TIMEOUT")

        except Exception as error:
            print(
                f"שגיאה: {error}"
            )

        time.sleep(
            SLEEP
        )

    # הסרת כפילויות זהות בלבד.
    # sourceClass נשאר במפתח בכוונה,
    # כי אותו שיעור יכול להופיע בכמה מערכות כיתתיות.
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

        unique_records[
            key
        ] = record

    records = list(
        unique_records.values()
    )

    day_order = {
        day: index
        for index, day in enumerate(
            DAYS
        )
    }

    records.sort(
        key=lambda r: (
            r["teacher"],
            day_order.get(
                r["day"],
                99
            ),
            r["hour"],
            r["subject"],
            r.get(
                "classroom",
                ""
            ),
            r.get(
                "sourceClass",
                ""
            ),
        )
    )

    teachers = sorted({
        record["teacher"]
        for record in records
        if record.get(
            "teacher"
        )
    })

    payload = {
        "updatedAt": datetime.now(
            timezone.utc
        ).isoformat(),

        "source": BASE_URL,

        "classes": sorted(
            classes
        ),

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

    print()
    print("=" * 60)

    print(
        f"✓ כיתות: "
        f"{len(classes)}"
    )

    print(
        f"✓ מורים: "
        f"{len(teachers)}"
    )

    print(
        f"✓ רשומות: "
        f"{len(records)}"
    )

    print(
        f"✓ נשמר: {OUT}"
    )

    print("=" * 60)
    print()

    if not classes:
        raise RuntimeError(
            "לא נמצאו כיתות."
        )

    if not records:
        raise RuntimeError(
            "לא נמצאו שיעורים."
        )


if __name__ == "__main__":
    main()
