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

### פלט בעברית

- **PDF:** גופן יוניקוד, יישור לימין, `python-bidi` לסדר תצוגה.
- **JSON:** `ensure_ascii=False`, ושמות שדות בעברית — למשל `מטא`, `נושאים`, לכל נושא `כותרת`, `שאלות`, ובכל שאלה `ניסוח`, `עקרון_בשאלה` (מסגרת העקרון שעליה נשענת ניסוח השאלה), `אפשרויות`, `אינדקס_תשובה_נכונה` (0–3), `משפט_מקור`. תוויות בדוח ה־PDF: **א–ד** במקום A–D.

אם רישום הגופן נכשל, התקן גופן או הגדר `QUIZ_SPIKE_HEBREW_FONT` לנתיב `.ttf` עם גליפים עבריים.

## What this proves

- Text extraction and a **first-pass topic split** (heuristic, not semantic).
- **Deterministic MCQs** grounded on extracted sentences: correct line from the topic; distractors sampled from other topics. **Question stems** are framed around **principles** (עקרון / עיקרון when detected): traits, gains, “prices”, and roles (e.g. שחקן / פרשן / מאמן) when the source sentence or principle mentions involvement — not generic “which matches the topic”.
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

- Replace `build_mcqs_for_topic` with an LLM call + **frozen bank** JSON schema.
- Add **Google OAuth** and persistence (not in this spike).
