# Database

Phase 2 storage for AssessAI. Two files, applied in order.

| File | What it does |
|---|---|
| `schema.sql` | Tables, constraints, indexes, and the trigger keeping `assessments.max_marks` derived from its questions |
| `policies.sql` | Row Level Security — who can read and write what, plus the `student_questions` view |

Both are idempotent: re-running them is safe.

---

## Applying them

1. Open your project at [supabase.com](https://supabase.com) → **SQL Editor** → **New query**.
2. Paste the whole of `schema.sql`, run it. Expect `Success. No rows returned`.
3. New query, paste the whole of `policies.sql`, run it.
4. Check **Table Editor** — eight tables, each showing an **RLS enabled** badge.

Order matters: the policies reference tables the schema creates.

---

## What the policies actually enforce

The rules this app rests on are currently enforced in Python, in the service
layer. That is sound while the store is session state, because there is nothing
else that can reach the data. Once rows live in Supabase, PostgREST will answer
anyone holding the publishable key — so each rule is restated in the database:

- **A student sees their own work and nobody else's.** `submissions_select`, and
  the same rule inherited by `submission_answers` and `grading_results`.
- **A student never sees a model answer.** Students read questions through the
  `student_questions` view, which does not have `model_answer` or
  `marking_criteria` as columns. Not blanked — absent.
- **Only a teacher makes a score official.** `grading_results_update_teacher` is
  the review gate. A student may write an AI estimate for their own submission,
  but the insert policy forces it to be `awaiting_review` with no approved score.
- **Nobody promotes themselves to teacher.** `role` lives on `profiles` and is
  excluded from the column grant, so the update policy cannot touch it. Profiles
  are created by a service-role process at sign-up.
- **A study camp's baseline cannot be rebased.** There is no `UPDATE` policy on
  `study_camps` at all. A camp that started wrong is deleted and rebuilt, which
  is honest; the improvement figure is never quietly rewritten underneath it.

---

## The one gap

`student_questions` keeps model answers out of anything a student's session
reads. That is enough for a student working through their own typed-up set,
which has no model answers anyway.

It is **not** enough when a student's self-study upload is graded against a
teacher's assessment. Grading compares the answer to the model answer, so
whatever grades has to read it — and today that is `services/grading_service.py`,
running inside the student's own session. Streamlit executes it server-side, so
the answer is not shipped to the student's browser, but the credential that
fetched it is the student's, and the boundary is a Python function rather than
Postgres.

The fix is a Supabase Edge Function holding the service role: the session posts
a submission id, the function reads the model answer, grades, and writes back
the result — and the student's credential can never read the answer at all.
That is the next piece of work after the repository port. Until it lands, this
is the one rule enforced by convention rather than by the database.

---

## What is not yet tested

`tests/test_repository.py` drives `SupabaseRepository` against an in-memory fake
client. That proves the repository writes the right rows, batches its reads, and
replaces child rows instead of duplicating them — but it proves nothing about
the SQL above.

Whether these policies actually permit what they should, and refuse what they
should, needs an integration test signed in as a real student and a real teacher
against a live project. Until that exists, treat the policy file as reviewed but
unexercised.

---

## Keys

The app needs `SUPABASE_URL` and `SUPABASE_ANON_KEY` (the publishable key) in
`.env`. The **secret** key belongs in neither `.env` nor this repository — it
bypasses every policy above. It is for the sign-up and grading functions, held
in Supabase's own secret storage.
