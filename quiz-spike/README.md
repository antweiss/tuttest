# Quiz technical spike (PDF → topics → MCQs → PDF)

End-to-end **offline** pipeline to de-risk the product shape: ingest a coaching PDF, split into coarse topics, build **7 multiple-choice questions per topic** without auth, and write a **PDF report** plus machine-readable JSON.

## Setup

```bash
cd quiz-spike
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python spike_pipeline.py --pdf /Users/antweiss/Downloads/tut.pdf --out ../_bmad-output/quiz-spike-out
```

Defaults: `--pdf` can be omitted if you set `QUIZ_SPIKE_PDF` to an absolute path.

### נושאים: פחות פרקים בחידון

ברירת מחדל: עד **12 נושאים** — ממזגים פרקים סמוכים מתוכן העניינים/Outline (מספר הפרקים המקורי מופיע ב־`מקור_חלוקת_נושאים` כ־`אוחד מ־N פרקים`).

| דגל | משמעות |
|-----|--------|
| `--max-topics 12` | תקרה (0 = בלי מיזוג) |
| `--outline-max-level 2` | עומק בסימניות PDF (1 = ראשי בלבד) |
| `--text-toc-max-entries 48` | כמה שורות TOC לקרוא מהטקסט |

### שאלות מנוסחות ב־LLM (OpenAI)

הספייק המקורי בונה שאלות **יוריסטיות** ממשפטים בחומר (מהיר, ללא רשת). לשאלות שנכתבות כולן על ידי מודל:

```bash
export OPENAI_API_KEY=sk-...
# אופציונלי: export QUIZ_SPIKE_OPENAI_MODEL=gpt-4o-mini
python llm_mcq.py --pdf /path/to/tut.pdf --out ../_bmad-output/quiz-spike-llm
```

פלט: אותו `spike_bank.json` + `spike_report.pdf`. אותם דגלי `--max-topics` / outline / TOC כמו ב־`spike_pipeline.py`. דורש רשת ומפתח API.

### פלט בעברית

- **PDF:** גופן יוניקוד, יישור לימין, `python-bidi` לסדר תצוגה.
- **JSON:** `ensure_ascii=False`, ושמות שדות בעברית — למשל `מטא`, `נושאים`, לכל נושא `כותרת`, `שאלות`, ובכל שאלה `ניסוח`, `עקרון_בשאלה` (מסגרת העקרון שעליה נשענת ניסוח השאלה), `אפשרויות`, `אינדקס_תשובה_נכונה` (0–3), `משפט_מקור`. תוויות בדוח ה־PDF: **א–ד** במקום A–D.

אם רישום הגופן נכשל, התקן גופן או הגדר `QUIZ_SPIKE_HEBREW_FONT` לנתיב `.ttf` עם גליפים עבריים.

## What this proves

- Text extraction and **topic split** from PDF outline, Hebrew TOC in text, or paragraph fallback — with an optional **cap + merge** so the quiz stays navigable.
- **Deterministic MCQs** grounded on extracted sentences: correct line from the topic; distractors sampled from other topics. **Question stems** are framed around **principles** (עקרון / עיקרון when detected): traits, gains, “prices”, and roles (e.g. שחקן / פרשן / מאמן) when the source sentence or principle mentions involvement — not generic “which matches the topic”.
- Optional **`llm_mcq.py`**: same topic resolution, **LLM-authored** stems and choices (OpenAI API).
- **PDF artifact** suitable for an owner demo (label as draft / AI-assisted in the doc header).

## דמו ווב (בחירת נושא → חידון → ציון)

מתיקיית `web/`:

1. העתק את בנק השאלות לשם בשם `spike_bank.json` (או העבר כתובת ב־`?bank=`):

```bash
cp ../_bmad-output/quiz-spike-out/spike_bank.json web/spike_bank.json
cd web && python3 -m http.server 8765
```

2. פתח בדפדפן: `http://127.0.0.1:8765/`  
   קישור ישיר לנושא (אחרי טעינה): `#quiz/t0` (מזהים מ־`מזהה_נושא` ב־JSON).

ללא שרת HTTP, `fetch` לקובץ JSON לרוב ייכשל מ־`file://` — השתמש בשרת המקומי.

הדמו שומר **התקדמות ותוצאות** ב־`sessionStorage` (רענון ב־`#quiz/...` או `#results`); אם מספר הנושאים או הבנק השתנה, הסשן לא משוחזר.

### Netlify (מ־GitHub)

בשורש ה-repo יש `netlify.toml` שמפרסם את `quiz-spike/web/` (כולל `spike_bank.json`).  
ב־[Netlify](https://app.netlify.com/) → Add new site → Import from Git → בחר את ה-repo `antweiss/tuttest` — אין צורך ב־Base directory מיוחד; הבילד ריק והפרסום לפי ה־TOML.

## Next spike hooks

- Human review / rubric for LLM banks; optional **frozen JSON schema** validation in CI.
- Add **Google OAuth** and persistence (not in this spike).
