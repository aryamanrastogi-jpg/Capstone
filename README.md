# AssessAI

**Teacher-reviewed AI assessment support for Grades 7–9.**

AssessAI is a teacher-facing, AI-assisted assessment platform. Teachers supply the
questions, model answers, marking criteria and student responses; the system returns
suggested scores, identified errors and draft student-friendly feedback.

> **Every AI-generated result is a recommendation.** A teacher must review and approve
> each score and each piece of feedback before it is finalised. Nothing is auto-published.

The initial subject is mathematics, but the models and services are structured so that
further subjects can be added without a rewrite.

---

## Product purpose

Marking is the slowest part of a teacher's week, and the feedback students actually
need — *what* went wrong and *why* — is the first thing that gets cut when time runs
short. AssessAI drafts that feedback so the teacher's time goes into judgement rather
than transcription, while keeping the teacher firmly in control of every mark awarded.

---

## Current MVP scope (Phase 1)

This repository contains a **runnable Streamlit MVP foundation**: the complete interface
and workflow, driven by anonymised sample data and a deterministic mock grader.

**What is real in this phase**

- All six pages, fully navigable and populated with sample data
- Pydantic data models with enforced score and confidence bounds
- A deterministic, rule-based grading service (no LLM, no network calls)
- Digital PDF and plain-text extraction via PyMuPDF
- The full teacher review loop: accept, edit, flag
- Analytics driven only by teacher-approved results
- A template-based practice question generator

**What is deliberately mocked or deferred**

- No real LLM is called. `grading_service.grade_answer` is the single seam to replace.
- No Supabase persistence. Session state is the store; the client module is scaffolded.
- No handwriting OCR, no image-based answer interpretation.

---

## Features

| Page | What it does |
|---|---|
| **Dashboard** | Assessment and submission counts, items awaiting review, average class score, recent activity, and the most common error categories. |
| **Create Assessment** | Enter title, subject, curriculum, grade, topic, then add questions with model answers, marking criteria and marks via `st.data_editor`. Validates required fields and computes the total automatically. |
| **Upload Responses** | Select an assessment, enter an anonymous student code, then paste an answer or upload a TXT / digital PDF. Extracted text is previewed and editable before confirming. |
| **Review Grading** | Shows the question, model answer, marking criteria, student response, suggested score, confidence, correct elements, detected errors, draft feedback and a teacher note. The teacher accepts, edits, or flags. |
| **Analytics** | Average score, score distribution, hardest questions, most frequent error categories, topics needing revision, and the share of AI scores accepted without editing. |
| **Practice Generator** | Deterministic templates that build targeted follow-up practice from a topic, an error category and a difficulty. |

### Review states

| Badge | Meaning |
|---|---|
| ⏳ Awaiting review | The AI has suggested a score. It counts for nothing yet. |
| ✓ Approved | The teacher accepted the AI recommendation unchanged. |
| ✎ Edited by teacher | The teacher changed the score and/or the wording. |
| ⚑ Flagged | Parked for a second look. **Excluded from analytics and never treated as a mark.** |

---

## Technology stack

Python 3.11+ · Streamlit · Pydantic · Pandas · Plotly · PyMuPDF · python-dotenv ·
Supabase Python client · Pytest

The whole application runs as a single Streamlit project. There is no separate frontend,
backend, or API server.

---

## Folder structure

```text
.
├── app.py                      # entry point: page config, state init, navigation
├── pages/
│   ├── dashboard.py
│   ├── create_assessment.py
│   ├── upload_responses.py
│   ├── review_grading.py
│   ├── analytics.py
│   └── practice_generator.py
├── components/
│   ├── layout.py               # page header, sidebar status, metrics, empty states
│   ├── navigation.py           # st.Page / st.navigation definitions
│   └── status_badges.py        # review, submission and confidence badges
├── models/
│   ├── assessment.py           # Assessment, Question, Subject
│   ├── submission.py           # Submission, SubmissionStatus
│   └── grading.py              # GradingResult, ErrorItem, ErrorType, ReviewStatus
├── services/
│   ├── assessment_service.py   # storage for assessments, submissions, results
│   ├── grading_service.py      # deterministic mock grader + teacher decisions
│   ├── document_service.py     # TXT / digital-PDF text extraction
│   ├── analytics_service.py    # pure Pandas computations
│   ├── practice_service.py     # template practice generator
│   ├── state.py                # central session-state initialisation
│   └── supabase_client.py      # optional Supabase client, demo-mode fallback
├── data/
│   └── sample_data.py          # anonymised seed dataset
├── utils/
│   ├── config.py               # settings, upload limits, notices
│   └── validation.py           # draft, upload and filename validation
├── tests/
│   ├── test_grading.py
│   └── test_validation.py
├── .streamlit/config.toml
├── .env.example
├── requirements.txt
└── README.md
```

`pages/` holds the page scripts, but the menu is defined entirely in
`components/navigation.py`. Because `app.py` calls `st.navigation`, Streamlit's automatic
`pages/` directory discovery is bypassed, so there is exactly one source of truth for the
navigation.

---

## Local setup

### 1. Requirements

Python 3.11 or newer. Check with:

```bash
python --version
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

```bash
py -3 -m venv .venv
```

```bash
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
streamlit run app.py
```

The app opens at <http://localhost:8501>. No credentials are needed — it starts in demo
mode with sample data already loaded.

---

## Demo mode

If `SUPABASE_URL` and `SUPABASE_ANON_KEY` are absent, the app runs in **demo mode**:

- A **Demo Mode** badge is shown in the sidebar, with a one-line explanation.
- An anonymised sample dataset (3 assessments, 10 submissions, mixed review states) is
  seeded on first launch.
- All data lives in Streamlit session state and is lost when the session ends. Use the
  sidebar **Reset demo data** button to restore the seed set at any time.

Demo mode is never silent. The sidebar always says which backend is in use, and if
credentials are present but the connection fails, that is reported as an error rather
than being swallowed.

**Note on persistence:** a full browser reload starts a new Streamlit session and
re-seeds the sample data. Data persists while you move between pages using the sidebar
navigation, which is how the app is meant to be used in this phase.

---

## Environment variables

Copy the template and edit your local copy:

```bash
cp .env.example .env
```

```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
LLM_API_KEY=
LLM_MODEL=
```

- All four are **optional**. The app runs fully without any of them.
- The `LLM_*` variables are **placeholders only**. No AI calls are made in this phase.
- `.env` is git-ignored. Never commit real credentials.

---

## Running the tests

```bash
python -m pytest
```

For a verbose run:

```bash
python -m pytest -v
```

The suite (83 tests) covers:

- Negative scores and scores above the maximum are rejected
- Confidence must stay within 0–1
- Valid grading results pass validation
- Assessment totals are computed from the questions
- Unsupported upload formats are rejected, including content that contradicts its
  extension
- Filenames are sanitised (path traversal, Windows separators, unsafe characters)
- The mock grading service returns valid, deterministic, structured output
- AI output is never auto-approved; flagged results never yield a final score
- Digital PDFs are extracted; image-only PDFs are reported clearly
- Analytics count only teacher-approved results and handle an empty dataset
- Generated practice questions resolve to clean, whole-number answers

---

## Security and privacy

This is a prototype. It is built to be used with **anonymised or synthetic student work
only**, and a notice to that effect appears on every page.

- Students are identified by anonymous codes (`S-8201`), never by name
- The sample dataset contains no real student data
- Environment variables are never rendered in the UI or written to logs
- Uploads are restricted to `.txt` and `.pdf`, capped at 5 MB
- File **content** is checked against the claimed extension — a `.pdf` that is not a PDF,
  or a `.txt` that is really a PDF, is rejected
- Uploaded filenames are sanitised before use (directory components stripped, unsafe
  characters replaced)

---

## Current limitations

- **No real AI.** Grading is rule-based keyword and numeric matching. It is deterministic
  and explainable, but it is not a substitute for a language model — it can misjudge a
  correct answer phrased unusually. This is precisely why teacher review is mandatory.
- **One response per submission.** A submission is a single block of text assessed against
  every question, rather than per-question segmentation.
- **No persistence.** Session state only; data is lost when the session ends.
- **No handwriting or image support.** Scanned and photographed pages are detected and
  rejected with an explanation, not guessed at.
- **No authentication.** The teacher identity is a fixed placeholder.
- **Practice generator is template-based**, limited to the six built-in topics.

---

## Planned next steps

1. Replace `grading_service.grade_answer` with a real LLM call, keeping the
   `GradingResult` contract and the mandatory review gate unchanged.
2. Implement Supabase persistence behind the existing `assessment_service` function
   signatures, so no page code changes.
3. Segment submissions per question rather than grading one block against every question.
4. Add teacher authentication and per-teacher data scoping.
5. Export approved results and feedback to CSV / PDF report cards.
6. Replace the template practice generator with an AI service driven by each student's
   actual error history.
