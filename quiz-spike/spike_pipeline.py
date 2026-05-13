#!/usr/bin/env python3
"""
ספייק: PDF → נושאים → שאלות רב-ברירה → JSON + PDF (ללא רשת לאחר התקנת תלויות).
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from bidi.algorithm import get_display
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

# תוויות ברירה בעברית (במקום A–D)
CHOICE_LABELS = ("א", "ב", "ג", "ד")


@dataclass
class MCQ:
    topic: str
    stem: str
    choices: list[str]
    correct_index: int
    source_sentence: str
    principle_in_stem: str = ""


def extract_text_from_document(doc: fitz.Document) -> str:
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text("text"))
    return "\n".join(parts)


def extract_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    try:
        return extract_text_from_document(doc)
    finally:
        doc.close()


def _extract_page_range(doc: fitz.Document, start_0: int, end_0_inclusive: int) -> str:
    start_0 = max(0, min(start_0, doc.page_count - 1))
    end_0_inclusive = max(start_0, min(end_0_inclusive, doc.page_count - 1))
    parts: list[str] = []
    for pno in range(start_0, end_0_inclusive + 1):
        parts.append(doc.load_page(pno).get_text("text"))
    return "\n".join(parts)


def topics_from_pdf_outline(
    doc: fitz.Document,
    max_level: int = 2,
    min_body_chars: int = 60,
) -> list[tuple[str, str]] | None:
    """
    נושאים לפי סימניות / Outline של ה-PDF (אם קיים).
    """
    toc = doc.get_toc(simple=True)
    if not toc or len(toc) < 2:
        return None

    entries: list[tuple[int, str, int]] = []
    for row in toc:
        if not row or len(row) < 3:
            continue
        lvl, title, page = int(row[0]), str(row[1]).strip(), int(row[2])
        if lvl > max_level:
            continue
        if len(title) < 2:
            continue
        low = title.casefold()
        if low in (
            "contents",
            "table of contents",
            "תוכן עניינים",
            "תוכן העניינים",
        ):
            continue
        entries.append((lvl, title, page))

    if len(entries) < 2:
        return None

    topics: list[tuple[str, str]] = []
    for i, (_lvl, title, page_1) in enumerate(entries):
        start_0 = page_1 - 1
        if i + 1 < len(entries):
            next_p1 = entries[i + 1][2]
            end_0 = next_p1 - 2
        else:
            end_0 = doc.page_count - 1
        if end_0 < start_0:
            end_0 = start_0
        body = _extract_page_range(doc, start_0, end_0)
        if len(body.strip()) < min_body_chars:
            continue
        topics.append((title, body[:50_000]))

    return topics if len(topics) >= 2 else None


_TOC_ANCHOR = re.compile(
    r"תוכן\s+ה(?:עניינים|ענינים|עיניינים|עינייניפ|יניינים)\b",
    re.IGNORECASE,
)
_TOC_DOTTED_LINE = re.compile(
    r"^(?P<title>.{2,240}?)\s*(?:\.{2,}|…+)\s*(?P<page>\d{1,4})\s*$"
)
_TOC_NUMBERED_LINE = re.compile(
    r"^\s*(?P<num>\d{1,2})\s*[.\u05bf\u05c0\u0591-\u05c7]*\s*(?P<title>.{2,240}?)\s+(?P<page>\d{1,4})\s*$"
)


def _clean_toc_title(parts: list[str]) -> str:
    t = " ".join(p.strip() for p in parts if p.strip())
    t = re.sub(r"\s+", " ", t).strip(" .-־")
    return t


def _is_dot_leader_line(s: str) -> bool:
    """שורה של נקודות/רווחים בלי טקסט משמעותי (לפני מספר עמוד)."""
    t = s.strip()
    if len(t) < 2:
        return False
    return bool(re.fullmatch(r"[.\s…׳·]+", t)) and "." in t


def _parse_toc_multiline_block(
    lines: list[str], max_page: int
) -> list[tuple[str, int]] | None:
    """
    פורמט נפוץ ב-PDF עברי: כותרת בשורה/שורות, אחריה שורות נקודות, ואז מספר עמוד.
    דוגמה: 'קצת עלינו.' / '....' / '  4'
    """
    items: list[tuple[str, int]] = []
    i = 0
    L = len(lines)
    empty_streak = 0
    while i < L:
        while i < L and not lines[i].strip():
            i += 1
            empty_streak += 1
            if empty_streak > 25 and items:
                return items
        empty_streak = 0
        if i >= L:
            break
        s = lines[i].strip()
        if _is_dot_leader_line(s):
            i += 1
            continue
        # שורת TOC קלאסית בשורה אחת
        dm = _TOC_DOTTED_LINE.match(s)
        if dm:
            title = re.sub(r"\s+", " ", dm.group("title")).strip(" .-־")
            pg = int(dm.group("page"))
            if 1 <= pg <= max_page and len(title) >= 2:
                items.append((title, pg))
            i += 1
            continue
        nm = _TOC_NUMBERED_LINE.match(s)
        if nm:
            title = re.sub(r"\s+", " ", nm.group("title")).strip(" .-־")
            pg = int(nm.group("page"))
            if 1 <= pg <= max_page and len(title) >= 2:
                items.append((title, pg))
            i += 1
            continue

        # כותרת מרובת שורות עד בלוק נקודות
        title_lines: list[str] = []
        while i < L:
            s2 = lines[i].strip()
            if not s2:
                i += 1
                continue
            if _is_dot_leader_line(s2):
                break
            if re.fullmatch(r"\d{1,4}", s2) and title_lines:
                break
            title_lines.append(s2)
            i += 1

        title = _clean_toc_title(title_lines)
        if len(title) < 2:
            continue

        while i < L and not lines[i].strip():
            i += 1
        page: int | None = None
        while i < L:
            s3 = lines[i].strip()
            if not s3:
                i += 1
                continue
            m = re.fullmatch(r"[\s.…]+(\d{1,4})", s3)
            if m:
                page = int(m.group(1))
                i += 1
                break
            if _is_dot_leader_line(s3):
                i += 1
                continue
            if re.fullmatch(r"\d{1,4}", s3):
                page = int(s3)
                i += 1
                break
            break

        if page is not None and 1 <= page <= max_page:
            items.append((title, page))
        if len(items) >= 80:
            break

    return items if len(items) >= 2 else None


def topics_from_text_toc(
    raw_text: str,
    doc: fitz.Document,
    min_body_chars: int = 60,
    max_entries: int = 48,
) -> list[tuple[str, str]] | None:
    """
    מזהה בלוק 'תוכן העניינים' / 'תוכן הענינים' בטקסט; תומך ב-TOC מפוצל לשורות.
    """
    m = _TOC_ANCHOR.search(raw_text)
    if not m:
        return None

    window_lines = raw_text[m.end() : m.end() + 25_000].splitlines()
    parsed = _parse_toc_multiline_block(window_lines, doc.page_count)
    if not parsed:
        return None

    items = parsed[:max_entries]
    items.sort(key=lambda x: x[1])
    deduped: list[tuple[str, int]] = []
    seen: set[int] = set()
    for title, pg in items:
        if pg in seen:
            continue
        seen.add(pg)
        deduped.append((title, pg))
    items = deduped
    if len(items) < 2:
        return None

    topics: list[tuple[str, str]] = []
    for i, (title, page_1) in enumerate(items):
        start_0 = page_1 - 1
        if i + 1 < len(items):
            next_p1 = items[i + 1][1]
            end_0 = next_p1 - 2
        else:
            end_0 = doc.page_count - 1
        if end_0 < start_0:
            end_0 = start_0
        body = _extract_page_range(doc, start_0, end_0)
        if len(body.strip()) < min_body_chars:
            continue
        topics.append((title, body[:50_000]))

    return topics if len(topics) >= 2 else None


def merge_topics_to_max(
    topics: list[tuple[str, str]], max_topics: int
) -> list[tuple[str, str]]:
    """
    מיזוג נושאים סמוכים כדי לא לחרוג מ־max_topics (חידון קריא).
    max_topics <= 0 — ללא מיזוג.
    """
    if max_topics <= 0 or len(topics) <= max_topics:
        return topics
    n = len(topics)
    chunk = max(1, math.ceil(n / max_topics))
    out: list[tuple[str, str]] = []
    for i in range(0, n, chunk):
        group = topics[i : i + chunk]
        titles = [t[0] for t in group]
        if len(group) == 1:
            title = titles[0]
        else:
            title = f"{titles[0]} · עוד {len(group) - 1} פרקים"
        body = "\n\n----\n\n".join(t[1] for t in group)
        out.append((title[:220], body[:50_000]))
    return out


def resolve_topics_list(
    doc: fitz.Document,
    raw: str,
    text: str,
    *,
    outline_max_level: int,
    text_toc_max_entries: int,
) -> tuple[str, list[tuple[str, str]]]:
    """
    אותו סדר עדיפות כמו ב-main: Outline → TOC בטקסט → פסקאות.
    """
    topic_source = "יוריסטיקת פסקאות (גיבוי)"
    topics = topics_from_pdf_outline(doc, max_level=outline_max_level)
    if topics:
        topic_source = "סימניות PDF (Outline)"
    else:
        topics = topics_from_text_toc(raw, doc, max_entries=text_toc_max_entries)
        if topics:
            topic_source = "תוכן עניינים מהטקסט"
        else:
            topics = segment_topics(text)
    return topic_source, topics


def normalize_text(raw: str) -> str:
    t = raw.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def split_sentences(block: str) -> list[str]:
    # נקודה, סימן שאלה וסימן קריאה (ASCII ויוניקוד עברי)
    chunks = re.split(r"(?<=[.!?。．!?])\s+", block)
    out = [c.strip() for c in chunks if len(c.strip()) > 40]
    return out[:200]


def segment_topics(text: str, max_topics: int = 16, min_chars: int = 900) -> list[tuple[str, str]]:
    """
    חלוקת נושאים גסה: מיזוג פסקאות עד min_chars.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 80]
    if not paragraphs:
        return [("כל המסמך", text[:12000])]

    topics: list[tuple[str, str]] = []
    buf: list[str] = []
    buf_len = 0
    for p in paragraphs:
        if buf_len + len(p) < min_chars:
            buf.append(p)
            buf_len += len(p) + 2
            continue
        blob = "\n\n".join(buf)
        title_line = blob.split("\n", 1)[0].strip()[:120]
        topics.append((title_line or f"נושא {len(topics)+1}", blob[:20000]))
        buf = [p]
        buf_len = len(p)
    if buf:
        blob = "\n\n".join(buf)
        title_line = blob.split("\n", 1)[0].strip()[:120]
        topics.append((title_line or f"נושא {len(topics)+1}", blob[:20000]))

    if len(topics) > max_topics:
        step = max(1, len(topics) // max_topics)
        merged: list[tuple[str, str]] = []
        for i in range(0, len(topics), step):
            chunk = topics[i : i + step]
            title = chunk[0][0]
            body = "\n\n".join(t[1] for t in chunk)
            merged.append((f"{title} (מאוחד)", body[:20000]))
        topics = merged[:max_topics]
    return topics


def other_topic_sentences(
    topics: list[tuple[str, str]], skip_index: int
) -> list[str]:
    pool: list[str] = []
    for i, (_, body) in enumerate(topics):
        if i == skip_index:
            continue
        pool.extend(split_sentences(body))
    return pool


# תפקידים מהאנלוגיה (כדורגל / חיים) — לניסוח שאלות על עקרונות
ROLE_WORDS = ("שחקן", "פרשן", "מאמן", "מתאמן", "מאמנים", "שחקנים", "השחקן", "המאמן")


def _roles_hint(sentence: str) -> str | None:
    hits: list[str] = []
    for w in ROLE_WORDS:
        if w in sentence and w not in hits:
            hits.append(w)
    if not hits:
        return None
    if {"שחקן", "פרשן", "מאמן"}.issubset(set(hits)) or len(hits) >= 3:
        return "שחקן, פרשן ומאמן (אנלוגיית הכדורגל)"
    return " ו".join(hits) if len(hits) <= 3 else ", ".join(hits[:4])


def extract_principles_from_body(body: str) -> list[str]:
    """מחלץ כותרות עקרון / עיקרון כפי שמופיעות בטקסט."""
    found: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(
        r"(עיקרון|עקרון)\s+([\u0590-\u05FF](?:[^\n•]{0,46}[\u0590-\u05FFa-zA-Zא-ת])?)",
        body,
    ):
        raw = f"{m.group(1)} {m.group(2).strip()}"
        raw = re.sub(r"\s+", " ", raw).strip(" .-־,:;")
        if len(raw) < 6 or len(raw) > 58:
            continue
        key = re.sub(r"\s+", "", raw).casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append(raw[:56])
        if len(found) >= 24:
            break
    return found


def _principle_norm_key(s: str) -> str:
    t = re.sub(r"\s+", "", s)
    return t.replace("עיקרון", "עקרון").casefold()


def principle_lens_for_topic(topic_title: str, body: str) -> list[str]:
    """רשימת עקרונות לסיבוב בין שאלות; אם אין — כותרת הפרק או תווית כללית."""
    tt = topic_title.strip()
    # פרק שמוקדס סביב עקרון יחיד — כל השאלות נשענות על כותרת הפרק (לא סיבוב על עקרונות אחרים מאותו עמוד)
    if re.match(r"(עיקרון|עקרון)\s+", tt) and "עקרונות" not in tt:
        return [tt[:56]]

    xs = extract_principles_from_body(body)
    if re.search(r"עיקרון|עקרון", tt):
        if not any(_principle_norm_key(x) == _principle_norm_key(tt) for x in xs):
            xs.insert(0, tt[:56])
    if not xs:
        xs = [tt[:56] if len(tt) > 3 else "העקרונות בפרק"]
    out: list[str] = []
    seen: set[str] = set()
    for x in xs:
        k = _principle_norm_key(x)
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def stem_principle_focused(
    topic_title: str,
    principle: str,
    sentence: str,
    q_index: int,
) -> str:
    """
    שאלה מנוסחת סביב עקרון (מאפיינים, רווחים, מחירים, תפקידים) — לא 'התאמה לנושא'.
    התשובה הנכונה נשארת משפט מהמקור.
    """
    p = principle[:52]
    tshort = topic_title[:44]
    roles = _roles_hint(sentence)
    involvement = "מעורבות" in p or "מעורבות" in topic_title

    pool: list[str] = []

    if involvement or roles:
        pool.extend(
            [
                f'בהקשר של «{p}» וביחס לתפקידי שחקן / פרשן / מאמן — איזו טענה מהטקסט מתארת נכון מאפיין, רווח או "מחיר" של התפקיד?',
                f"לגבי «{p}» — איזו טענה משקפת נכון את יחסי הרווחים והעלויות בין תפקידים במצב המתואר?",
                f"כשמנתחים את «{p}» דרך מאפייני השחקן, הפרשן והמאמן — מה נכון לפי החומר?",
            ]
        )
    if roles and not involvement:
        pool.append(
            f'לגבי תפקידי {roles} ביחס ל«{p}» — איזו טענה תואמת את החומר?',
        )

    pool.extend(
        [
            f"לגבי «{p}» — איזו טענה מהטקסט משקפת נכון מאפיין, דגש או השלכה עקרונית?",
            f"בהקשר של «{p}» — איזו טענה מתארת רווח, יתרון או תועלת שעולה מהחומר?",
            f'לגבי «{p}» — איזו טענה נוגעת לעלות, מחיר או "מחיר תודתי" של בחירה בהתנהגות?',
            f"מה נכון לגבי יישום או משמעות של «{p}» בפרק?",
            f"איזו טענה מבטאת הכי טוב את רוח «{p}» כפי שהיא באה לידי ביטוי בטקסט?",
        ]
    )
    if not re.search(r"עיקרון|עקרון", p):
        pool.append(
            f'בנושא «{tshort}» — איזו טענה נתמכת בצורה הטובה ביותר בטקסט לגבי הרעיון או העקרון המרכזי?',
        )

    return pool[q_index % len(pool)]


def build_mcqs_for_topic(
    topic_title: str,
    topic_body: str,
    topics: list[tuple[str, str]],
    topic_index: int,
    rng: random.Random,
) -> list[MCQ]:
    sentences = split_sentences(topic_body)
    if len(sentences) < 7:
        pad = " ".join(sentences) or topic_body
        while len(sentences) < 7:
            sentences.append(pad[:400])

    distractor_pool = other_topic_sentences(topics, topic_index)
    if len(distractor_pool) < 9:
        distractor_pool.extend(sentences[::-1])

    principles = principle_lens_for_topic(topic_title, topic_body)

    mcqs: list[MCQ] = []
    for i in range(7):
        correct = sentences[i]
        principle = principles[i % len(principles)]
        stem = stem_principle_focused(topic_title, principle, correct, i)
        wrong = rng.sample(distractor_pool, k=min(3, len(distractor_pool)))
        while len(wrong) < 3:
            wrong.append(wrong[-1] + " (חלופה)")
        choices = [correct] + wrong[:3]
        order = list(range(4))
        rng.shuffle(order)
        shuffled = [choices[j] for j in order]
        correct_index = order.index(0)
        mcqs.append(
            MCQ(
                topic=topic_title,
                stem=stem,
                choices=shuffled,
                correct_index=correct_index,
                source_sentence=correct[:500],
                principle_in_stem=principle[:120],
            )
        )
    return mcqs


def write_json(out_dir: Path, payload: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "spike_bank.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _hebrew_font_candidates() -> list[Path]:
    env = os.environ.get("QUIZ_SPIKE_HEBREW_FONT", "").strip()
    paths: list[Path] = []
    if env:
        paths.append(Path(env).expanduser())
    # macOS — Arial Unicode MS covers Hebrew
    paths.extend(
        [
            Path("/Library/Fonts/Arial Unicode.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path("/System/Library/Fonts/Supplemental/David.ttc"),
            Path("/System/Library/Fonts/Supplemental/David Bold.ttf"),
            Path("/System/Library/Fonts/Supplemental/Raanana.ttc"),
        ]
    )
    # Linux common
    paths.extend(
        [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansHebrew-Regular.ttf"),
        ]
    )
    return paths


def register_hebrew_font() -> str:
    """Register a TTF with Hebrew glyphs; return internal ReportLab font name."""
    name = "QuizHebrew"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    for candidate in _hebrew_font_candidates():
        if candidate.is_file():
            pdfmetrics.registerFont(TTFont(name, str(candidate)))
            return name
    raise SystemExit(
        "לא נמצאה גופנית עם תמיכה בעברית. התקן גופן או הגדר QUIZ_SPIKE_HEBREW_FONT "
        "לנתיב .ttf (למשל Arial Unicode, Noto Sans Hebrew או David)."
    )


def _rtl_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    """Visual order for RTL / mixed Hebrew; escape for ReportLab XML."""
    vis = get_display(text)
    safe = html.escape(vis, quote=False).replace("\n", "<br/>")
    return Paragraph(safe, style)


def write_pdf(out_dir: Path, meta: dict, topics_payload: list[dict]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "spike_report.pdf"
    font = register_hebrew_font()
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        name="HebrewTitle",
        parent=base["Title"],
        fontName=font,
        alignment=TA_RIGHT,
        fontSize=18,
        leading=22,
    )
    heading = ParagraphStyle(
        name="HebrewHeading",
        parent=base["Heading2"],
        fontName=font,
        alignment=TA_RIGHT,
        fontSize=14,
        leading=18,
    )
    body = ParagraphStyle(
        name="HebrewBody",
        parent=base["Normal"],
        fontName=font,
        alignment=TA_RIGHT,
        fontSize=11,
        leading=15,
    )
    small = ParagraphStyle(
        name="HebrewSmall",
        parent=base["BodyText"],
        fontName=font,
        alignment=TA_RIGHT,
        fontSize=10,
        leading=14,
    )
    meta_style = ParagraphStyle(
        name="HebrewMeta",
        parent=base["Normal"],
        fontName=font,
        alignment=TA_RIGHT,
        fontSize=10,
        leading=14,
    )
    story: list = []
    story.append(
        _rtl_paragraph(
            "דוח ספייק — בנק שאלות (טיוטה; יש לבדוק מול בעלי החומר)",
            title,
        )
    )
    story.append(Spacer(1, 12))
    story.append(
        _rtl_paragraph(
            f"קובץ מקור: {meta.get('קובץ_pdf', '')}\n"
            f"מספר נושאים: {meta.get('מספר_נושאים', 0)}\n"
            f"מקור חלוקת נושאים: {meta.get('מקור_חלוקת_נושאים', '')}",
            meta_style,
        )
    )
    story.append(Spacer(1, 18))

    for t in topics_payload:
        story.append(_rtl_paragraph(t["כותרת"], heading))
        story.append(Spacer(1, 8))
        for idx, q in enumerate(t["שאלות"], start=1):
            story.append(_rtl_paragraph(f"ש{idx}. {q['ניסוח']}", body))
            pr = (q.get("עקרון_בשאלה") or "").strip()
            if pr:
                story.append(
                    _rtl_paragraph(f"מסגרת עקרון בשאלה: {pr[:200]}", small)
                )
            for j, c in enumerate(q["אפשרויות"]):
                label = CHOICE_LABELS[j]
                line = f"{label}. {c[:800]}"
                story.append(_rtl_paragraph(line, small))
            ans = CHOICE_LABELS[q["אינדקס_תשובה_נכונה"]]
            story.append(_rtl_paragraph(f"תשובה נכונה: {ans}", small))
            story.append(Spacer(1, 10))
        story.append(Spacer(1, 14))

    SimpleDocTemplate(str(path), pagesize=letter).build(story)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(
        description="ספייק: PDF → נושאים → שאלות רב-ברירה → JSON ו־PDF"
    )
    ap.add_argument(
        "--pdf",
        default=os.environ.get("QUIZ_SPIKE_PDF", ""),
        help="נתיב מוחלט לקובץ PDF",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "_bmad-output" / "quiz-spike-out",
        help="תיקיית פלט ל־JSON ו־PDF",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="זרע לבחירת מסיחים (לשחזור תוצאות)",
    )
    ap.add_argument(
        "--max-topics",
        type=int,
        default=12,
        help="מקסימום נושאים בבנק; ממזג פרקי TOC/Outline סמוכים. 0 = ללא הגבלה.",
    )
    ap.add_argument(
        "--outline-max-level",
        type=int,
        default=2,
        help="עומק מקסימלי בסימניות PDF (1=ראשי בלבד, 2=תת-כותרות).",
    )
    ap.add_argument(
        "--text-toc-max-entries",
        type=int,
        default=48,
        help="מקסימום שורות תוכן עניינים לקרוא מהטקסט לפני חיתוך.",
    )
    args = ap.parse_args()
    if not args.pdf:
        ap.error("יש להעביר --pdf או להגדיר QUIZ_SPIKE_PDF לנתיב הקובץ.")

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.is_file():
        raise SystemExit(f"לא נמצא קובץ PDF: {pdf_path}")

    doc = fitz.open(pdf_path)
    try:
        raw = extract_text_from_document(doc)
        text = normalize_text(raw)
        topic_source, topics = resolve_topics_list(
            doc,
            raw,
            text,
            outline_max_level=args.outline_max_level,
            text_toc_max_entries=args.text_toc_max_entries,
        )
        n_before = len(topics)
        topics = merge_topics_to_max(topics, args.max_topics)
        merged_note = ""
        if args.max_topics > 0 and len(topics) < n_before:
            merged_note = f" (אוחד מ־{n_before} פרקים)"
    finally:
        doc.close()

    rng = random.Random(args.seed)

    topics_payload: list[dict] = []
    all_mcqs: list[MCQ] = []
    for i, (title, body) in enumerate(topics):
        mcqs = build_mcqs_for_topic(title, body, topics, i, rng)
        all_mcqs.extend(mcqs)
        topics_payload.append(
            {
                "מזהה_נושא": f"t{i}",
                "כותרת": title,
                "תצוגה_מקדימה": body[:400].replace("\n", " "),
                "שאלות": [
                    {
                        "ניסוח": m.stem,
                        "עקרון_בשאלה": m.principle_in_stem,
                        "אפשרויות": m.choices,
                        "אינדקס_תשובה_נכונה": m.correct_index,
                        "משפט_מקור": m.source_sentence,
                    }
                    for m in mcqs
                ],
            }
        )

    meta = {
        "קובץ_pdf": str(pdf_path),
        "מספר_נושאים": len(topics),
        "שאלות_לכל_נושא": 7,
        "מקור_חלוקת_נושאים": topic_source + merged_note,
        "מייצר": "ספייק מקומי — שאלות יוריסטיות ממשפטים בחומר (מסיחים משאר הנושאים); לשאלות מנוסחות מלאות השתמש ב־llm_mcq.py",
    }
    payload = {"מטא": meta, "נושאים": topics_payload}
    json_path = write_json(args.out, payload)
    pdf_path_out = write_pdf(args.out, meta, topics_payload)
    print(f"נכתב: {json_path}")
    print(f"נכתב: {pdf_path_out}")


if __name__ == "__main__":
    main()
