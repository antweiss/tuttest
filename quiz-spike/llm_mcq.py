#!/usr/bin/env python3
"""
PDF → אותה חלוקת נושאים כמו spike_pipeline → שאלות בעזרת LLM (OpenAI API).

דורש OPENAI_API_KEY בסביבה. אופציונלי: QUIZ_SPIKE_OPENAI_MODEL (ברירת מחדל gpt-4o-mini).

פלט: אותו מבנה JSON כמו spike_bank.json (מטא + נושאים עם 7 שאלות כל אחד).
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import fitz

from spike_pipeline import (
    extract_text_from_document,
    merge_topics_to_max,
    normalize_text,
    resolve_topics_list,
    write_json,
    write_pdf,
)

SYSTEM_HE = (
    "אתה עורך חידון בעברית לחומרי הדרכה. "
    "מחזיר רק JSON תקין UTF-8 ללא markdown וללא טקסט לפני או אחרי."
)

USER_TEMPLATE = """כותרת הנושא: {title}

להלן טקסט המקור (עד ~12000 תווים). על בסיסו בלבד — כתוב בדיוק 7 שאלות רב־ברירה בעברית.
לכל שאלה:
- "ניסוח": משפט שאלה ברור (לא ארוך מדי).
- "עקרון_בשאלה": מסגרת עקרונית קצרה (עד 120 תווים) שעליה נשענת השאלה.
- "אפשרויות": בדיוק 4 מחרוזות; אחת נכונה לפי החומר והשאר סבירות אך שגויות.
- "אינדקס_תשובה_נכונה": מספר שלם 0–3 (מיקום התשובה הנכונה במערך אפשרויות).
- "משפט_מקור": ציטוט קצר מהטקסט שמצדיק את התשובה הנכונה.

החזר אובייקט JSON עם מפתח יחיד "שאלות" שהוא מערך של 7 אובייקטים, כל אחד עם המפתחות הנ"ל.

טקסט המקור:
---
{body}
---
"""


def _openai_chat_json(
    api_key: str,
    model: str,
    user_content: str,
    timeout_s: int = 120,
) -> dict:
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_HE},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.35,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI HTTP {e.code}: {body[:800]}") from e
    except urllib.error.URLError as e:
        raise SystemExit(f"רשת / API: {e}") from e

    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise SystemExit(f"תשובת API לא צפויה: {raw!r}") from e

    if isinstance(content, str):
        return json.loads(content)
    raise SystemExit("תוכן הודעה לא מחרוזת JSON")


def _validate_question(q: dict, idx: int) -> None:
    need = ("ניסוח", "עקרון_בשאלה", "אפשרויות", "אינדקס_תשובה_נכונה", "משפט_מקור")
    for k in need:
        if k not in q:
            raise ValueError(f"שאלה {idx}: חסר מפתח {k}")
    opts = q["אפשרויות"]
    if not isinstance(opts, list) or len(opts) != 4:
        raise ValueError(f"שאלה {idx}: צריך בדיוק 4 אפשרויות")
    ci = q["אינדקס_תשובה_נכונה"]
    if not isinstance(ci, int) or ci not in (0, 1, 2, 3):
        raise ValueError(f"שאלה {idx}: אינדקס_תשובה_נכונה חייב להיות 0–3")


def generate_topic_questions(
    title: str,
    body: str,
    api_key: str,
    model: str,
) -> list[dict]:
    snippet = body[:12_000]
    user = USER_TEMPLATE.format(title=title, body=snippet)
    data = _openai_chat_json(api_key, model, user)
    arr = data.get("שאלות")
    if not isinstance(arr, list) or len(arr) != 7:
        n = len(arr) if isinstance(arr, list) else "לא-מערך"
        raise ValueError(f"נושא «{title[:40]}»: צריך בדיוק 7 שאלות, התקבל {n}")
    out: list[dict] = []
    for i, q in enumerate(arr, start=1):
        if not isinstance(q, dict):
            raise ValueError(f"שאלה {i} אינה אובייקט")
        _validate_question(q, i)
        out.append(
            {
                "ניסוח": str(q["ניסוח"]).strip(),
                "עקרון_בשאלה": str(q["עקרון_בשאלה"]).strip()[:120],
                "אפשרויות": [str(x).strip() for x in q["אפשרויות"]],
                "אינדקס_תשובה_נכונה": int(q["אינדקס_תשובה_נכונה"]),
                "משפט_מקור": str(q["משפט_מקור"]).strip()[:500],
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="PDF → נושאים (כמו ספייק) → שאלות בעזרת OpenAI Chat Completions"
    )
    ap.add_argument("--pdf", required=True, help="נתיב ל־PDF")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("llm_bank_out"),
        help="תיקייה ל־spike_bank.json ו־spike_report.pdf",
    )
    ap.add_argument(
        "--model",
        default=os.environ.get("QUIZ_SPIKE_OPENAI_MODEL", "gpt-4o-mini"),
        help="מזהה מודל OpenAI",
    )
    ap.add_argument(
        "--max-topics",
        type=int,
        default=12,
        help="כמו ב־spike_pipeline: מיזוג נושאים. 0 = ללא הגבלה.",
    )
    ap.add_argument("--outline-max-level", type=int, default=2)
    ap.add_argument("--text-toc-max-entries", type=int, default=48)
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.35,
        help="השהיה בין קריאות API (שניות)",
    )
    args = ap.parse_args()

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("הגדר OPENAI_API_KEY בסביבה.")

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.is_file():
        raise SystemExit(f"לא נמצא PDF: {pdf_path}")

    doc = fitz.open(str(pdf_path))
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

    topics_payload: list[dict] = []
    for i, (title, body) in enumerate(topics):
        print(f"LLM נושא {i + 1}/{len(topics)}: {title[:60]}…")
        qs = generate_topic_questions(title, body, api_key, args.model)
        topics_payload.append(
            {
                "מזהה_נושא": f"t{i}",
                "כותרת": title,
                "תצוגה_מקדימה": body[:400].replace("\n", " "),
                "שאלות": qs,
            }
        )
        if args.sleep > 0 and i + 1 < len(topics):
            time.sleep(args.sleep)

    meta = {
        "קובץ_pdf": str(pdf_path),
        "מספר_נושאים": len(topics),
        "שאלות_לכל_נושא": 7,
        "מקור_חלוקת_נושאים": topic_source + merged_note,
        "מייצר": f"LLM ({args.model}) — OpenAI Chat Completions; נושאים כמו spike_pipeline",
        "מודל_llm": args.model,
    }
    payload = {"מטא": meta, "נושאים": topics_payload}
    out_dir = Path(args.out).resolve()
    json_path = write_json(out_dir, payload)
    pdf_path_out = write_pdf(out_dir, meta, topics_payload)
    print(f"נכתב: {json_path}")
    print(f"נכתב: {pdf_path_out}")


if __name__ == "__main__":
    main()
