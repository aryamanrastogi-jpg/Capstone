-- AssessAI - Phase 2 Row Level Security
--
-- Apply this in the Supabase SQL editor AFTER db/schema.sql.
-- Safe to re-run.
--
-- WHAT THIS FILE IS FOR
--   Today the rules that matter - "a student never sees another student's
--   work", "a student never sees a model answer", "only a teacher can approve a
--   score" - are enforced in Python, in the service layer. That is fine while
--   the store is session state, because there is nothing else to talk to.
--   The moment the data lives in Supabase, the anon key is in the browser's
--   reach and PostgREST will answer anyone who asks. So every one of those
--   rules is restated here, in the database, where it holds regardless of what
--   the application does.
--
--   Read this file as the real specification of who can see what. The Python
--   is a convenience on top of it.
--
-- THE ONE HONEST GAP: see "MODEL ANSWERS" at the bottom.

begin;

-- ---------------------------------------------------------------------------
-- Helper functions
-- ---------------------------------------------------------------------------
-- These are `security definer` so they bypass RLS on profiles. Without that, a
-- policy on profiles that needs to look at profiles recurses forever.
--
-- `stable` lets the planner call them once per statement rather than per row.

create or replace function public.app_profile_id()
returns text
language sql
stable
security definer
set search_path = public
as $fn$
    select id from public.profiles where auth_user_id = auth.uid();
$fn$;

comment on function public.app_profile_id() is
    'The signed-in user''s application profile id, or null when not signed in.';

create or replace function public.app_is_teacher()
returns boolean
language sql
stable
security definer
set search_path = public
as $fn$
    select coalesce(
        (select role = 'teacher' from public.profiles where auth_user_id = auth.uid()),
        false);
$fn$;

-- The teacher whose roster the signed-in student is on. Null for a teacher.
create or replace function public.app_my_teacher_id()
returns text
language sql
stable
security definer
set search_path = public
as $fn$
    select teacher_id from public.profiles where auth_user_id = auth.uid();
$fn$;

-- Is this profile a student on the signed-in teacher's roster?
create or replace function public.app_teaches(student_profile_id text)
returns boolean
language sql
stable
security definer
set search_path = public
as $fn$
    select exists (
        select 1
          from public.profiles s
         where s.id = student_profile_id
           and s.teacher_id = public.app_profile_id()
    ) and public.app_is_teacher();
$fn$;

-- ---------------------------------------------------------------------------
-- Turn RLS on everywhere
-- ---------------------------------------------------------------------------
-- Enabling RLS with no policy denies everything. Each table below then opens
-- exactly the access it should have, and nothing wider.
alter table public.profiles           enable row level security;
alter table public.assessments        enable row level security;
alter table public.questions          enable row level security;
alter table public.submissions        enable row level security;
alter table public.submission_answers enable row level security;
alter table public.grading_results    enable row level security;
alter table public.study_camps        enable row level security;
alter table public.study_sessions     enable row level security;

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------
-- You can read yourself. A teacher can read their roster. A student cannot
-- enumerate their classmates - the anonymous codes are not a licence to browse.
drop policy if exists profiles_select_self on public.profiles;
create policy profiles_select_self on public.profiles
    for select to authenticated
    using (auth_user_id = auth.uid() or public.app_teaches(id));

-- A user may edit their own display name and year group.
drop policy if exists profiles_update_self on public.profiles;
create policy profiles_update_self on public.profiles
    for update to authenticated
    using (auth_user_id = auth.uid())
    with check (auth_user_id = auth.uid());

-- NOTE: there is deliberately NO insert policy and NO policy granting a change
-- of `role`. Profiles are created by a service-role process at sign-up, and the
-- role is assigned there. A user who could insert or update their own role
-- could make themselves a teacher and read the whole class - which is exactly
-- the hole demo mode has and Phase 2 exists to close.
--
-- The update policy above still technically permits writing `role`. Postgres
-- has no column-level RLS, so that is closed with a column grant instead:
revoke update on public.profiles from authenticated;
grant update (display_name, year_group) on public.profiles to authenticated;

-- ---------------------------------------------------------------------------
-- assessments
-- ---------------------------------------------------------------------------
-- A student sees: their own typed-up sets, plus the teacher-authored sets
-- belonging to the teacher whose roster they are on, plus the unowned seed set.
-- A teacher sees: their own, plus anything their students created.
drop policy if exists assessments_select on public.assessments;
create policy assessments_select on public.assessments
    for select to authenticated
    using (
        owner_id = public.app_profile_id()
        or (not student_created and owner_id is null)
        or (not student_created and owner_id = public.app_my_teacher_id())
        or public.app_teaches(owner_id)
    );

-- Anyone signed in can author a set, but only as themselves, and a student
-- cannot pass it off as teacher-authored (which would publish it to the class).
drop policy if exists assessments_insert_own on public.assessments;
create policy assessments_insert_own on public.assessments
    for insert to authenticated
    with check (
        owner_id = public.app_profile_id()
        and (student_created or public.app_is_teacher())
    );

drop policy if exists assessments_update_own on public.assessments;
create policy assessments_update_own on public.assessments
    for update to authenticated
    using (owner_id = public.app_profile_id())
    with check (owner_id = public.app_profile_id());

drop policy if exists assessments_delete_own on public.assessments;
create policy assessments_delete_own on public.assessments
    for delete to authenticated
    using (owner_id = public.app_profile_id());

-- ---------------------------------------------------------------------------
-- questions
-- ---------------------------------------------------------------------------
-- Direct reads are for teachers and for the person who authored the set. A
-- student reads questions through public.student_questions instead, which does
-- not carry the model answer. See "MODEL ANSWERS" at the bottom.
drop policy if exists questions_select on public.questions;
create policy questions_select on public.questions
    for select to authenticated
    using (
        exists (
            select 1 from public.assessments a
             where a.id = questions.assessment_id
               and (a.owner_id = public.app_profile_id() or public.app_is_teacher())
        )
    );

drop policy if exists questions_write on public.questions;
create policy questions_write on public.questions
    for all to authenticated
    using (
        exists (
            select 1 from public.assessments a
             where a.id = questions.assessment_id
               and a.owner_id = public.app_profile_id()
        )
    )
    with check (
        exists (
            select 1 from public.assessments a
             where a.id = questions.assessment_id
               and a.owner_id = public.app_profile_id()
        )
    );

-- ---------------------------------------------------------------------------
-- student_questions: what a student is allowed to read
-- ---------------------------------------------------------------------------
-- model_answer and marking_criteria are not columns of this view. Not blanked,
-- not filtered in the application - absent. A student querying this view cannot
-- ask for them, because from where they sit those columns do not exist.
--
-- The view is intentionally NOT `security_invoker`, so it runs as its owner and
-- bypasses the questions policy above. That means the visibility rule has to be
-- restated in its WHERE clause, which is what the second half of this does.
drop view if exists public.student_questions;
create view public.student_questions as
    select q.id,
           q.assessment_id,
           q.position,
           q.question_text,
           q.max_marks
      from public.questions q
      join public.assessments a on a.id = q.assessment_id
     where a.owner_id = public.app_profile_id()
        or (not a.student_created and a.owner_id is null)
        or (not a.student_created and a.owner_id = public.app_my_teacher_id())
        or public.app_teaches(a.owner_id);

grant select on public.student_questions to authenticated;

comment on view public.student_questions is
    'Questions without model answers or marking criteria. The student-facing read path.';

-- ---------------------------------------------------------------------------
-- submissions
-- ---------------------------------------------------------------------------
-- The rule the whole product rests on: a student sees their own work and
-- nobody else's. A teacher sees the work of the students on their roster.
drop policy if exists submissions_select on public.submissions;
create policy submissions_select on public.submissions
    for select to authenticated
    using (
        student_id = public.app_profile_id()
        or public.app_teaches(student_id)
    );

drop policy if exists submissions_insert_own on public.submissions;
create policy submissions_insert_own on public.submissions
    for insert to authenticated
    with check (
        student_id = public.app_profile_id()
        or public.app_teaches(student_id)
    );

drop policy if exists submissions_update on public.submissions;
create policy submissions_update on public.submissions
    for update to authenticated
    using (student_id = public.app_profile_id() or public.app_teaches(student_id))
    with check (student_id = public.app_profile_id() or public.app_teaches(student_id));

drop policy if exists submissions_delete_own on public.submissions;
create policy submissions_delete_own on public.submissions
    for delete to authenticated
    using (student_id = public.app_profile_id());

-- ---------------------------------------------------------------------------
-- submission_answers
-- ---------------------------------------------------------------------------
-- Answers inherit the visibility of the submission they belong to. Written as a
-- lookup rather than a duplicated rule so the two can never disagree.
drop policy if exists submission_answers_all on public.submission_answers;
create policy submission_answers_all on public.submission_answers
    for all to authenticated
    using (
        exists (
            select 1 from public.submissions s
             where s.id = submission_answers.submission_id
               and (s.student_id = public.app_profile_id()
                    or public.app_teaches(s.student_id))
        )
    )
    with check (
        exists (
            select 1 from public.submissions s
             where s.id = submission_answers.submission_id
               and (s.student_id = public.app_profile_id()
                    or public.app_teaches(s.student_id))
        )
    );

-- ---------------------------------------------------------------------------
-- grading_results
-- ---------------------------------------------------------------------------
-- Readable by the student it concerns and by their teacher.
drop policy if exists grading_results_select on public.grading_results;
create policy grading_results_select on public.grading_results
    for select to authenticated
    using (
        exists (
            select 1 from public.submissions s
             where s.id = grading_results.submission_id
               and (s.student_id = public.app_profile_id()
                    or public.app_teaches(s.student_id))
        )
    );

-- A student's self-study upload produces an AI estimate, so a student must be
-- able to write a grading row for their own submission. What they must NOT be
-- able to do is approve it: teacher_approved_score and review_status are the
-- difference between an estimate and a mark.
drop policy if exists grading_results_insert on public.grading_results;
create policy grading_results_insert on public.grading_results
    for insert to authenticated
    with check (
        exists (
            select 1 from public.submissions s
             where s.id = grading_results.submission_id
               and (s.student_id = public.app_profile_id()
                    or public.app_teaches(s.student_id))
        )
        and (
            public.app_teaches(
                (select s.student_id from public.submissions s
                  where s.id = grading_results.submission_id))
            -- A student may only ever insert an unreviewed, unapproved row.
            or (review_status = 'awaiting_review'
                and teacher_approved_score is null
                and teacher_approved_feedback is null)
        )
    );

-- Only a teacher updates a grading result. This is the review gate: the thing
-- that makes a score official is a teacher, and now the database agrees.
drop policy if exists grading_results_update_teacher on public.grading_results;
create policy grading_results_update_teacher on public.grading_results
    for update to authenticated
    using (
        exists (
            select 1 from public.submissions s
             where s.id = grading_results.submission_id
               and public.app_teaches(s.student_id)
        )
    )
    with check (
        exists (
            select 1 from public.submissions s
             where s.id = grading_results.submission_id
               and public.app_teaches(s.student_id)
        )
    );

-- ---------------------------------------------------------------------------
-- study_camps and study_sessions
-- ---------------------------------------------------------------------------
-- A camp is private to the student. A teacher can see that one exists and how
-- it is going, because that is the point of the oversight view.
drop policy if exists study_camps_select on public.study_camps;
create policy study_camps_select on public.study_camps
    for select to authenticated
    using (student_id = public.app_profile_id() or public.app_teaches(student_id));

drop policy if exists study_camps_insert_own on public.study_camps;
create policy study_camps_insert_own on public.study_camps
    for insert to authenticated
    with check (student_id = public.app_profile_id());

drop policy if exists study_camps_delete_own on public.study_camps;
create policy study_camps_delete_own on public.study_camps
    for delete to authenticated
    using (student_id = public.app_profile_id());

-- Deliberately no UPDATE policy on study_camps.
--
-- baseline_percentage is the number the whole improvement story is measured
-- against. If it can be edited after the fact, "I went from 60% to 90%" stops
-- being a claim about the student and becomes a claim about the last person to
-- touch the row. A camp that started from the wrong baseline is deleted and
-- created again, which is honest; it is not quietly rebased.

drop policy if exists study_sessions_select on public.study_sessions;
create policy study_sessions_select on public.study_sessions
    for select to authenticated
    using (
        exists (
            select 1 from public.study_camps c
             where c.id = study_sessions.camp_id
               and (c.student_id = public.app_profile_id()
                    or public.app_teaches(c.student_id))
        )
    );

-- The student owns their own progress: marking a day done, recording a score.
drop policy if exists study_sessions_write_own on public.study_sessions;
create policy study_sessions_write_own on public.study_sessions
    for all to authenticated
    using (
        exists (
            select 1 from public.study_camps c
             where c.id = study_sessions.camp_id
               and c.student_id = public.app_profile_id()
        )
    )
    with check (
        exists (
            select 1 from public.study_camps c
             where c.id = study_sessions.camp_id
               and c.student_id = public.app_profile_id()
        )
    );

commit;

-- ===========================================================================
-- MODEL ANSWERS - the gap this file does not close
-- ===========================================================================
-- public.student_questions keeps model answers out of anything a student's
-- session can read. That is the right shape, and it is enough for a student
-- working through their own typed-up set, which has no model answers anyway.
--
-- It is NOT enough the moment a student's self-study upload is graded against a
-- TEACHER's assessment. Grading compares the answer to the model answer, so
-- whatever performs the grading must be able to read it - and today grading
-- runs in `services/grading_service.py`, inside the student's own session.
--
-- Streamlit runs that Python on the server, not in the browser, so the model
-- answer is not literally shipped to the student's machine. But the credential
-- that fetched it is the student's, and the boundary is then a Python function
-- rather than the database. That is a weaker guarantee than everything else in
-- this file.
--
-- The fix is to move grading behind a Supabase Edge Function holding the
-- service role: the student's session posts a submission id, the function reads
-- the model answer, grades, and writes back a GradingResult - and the student's
-- credential is never able to read the answer at all. That is the next piece of
-- work after the repository port, and until it lands, this is the one rule
-- enforced by convention rather than by Postgres.
