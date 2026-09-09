-- AssessAI - Phase 2 schema
--
-- Apply this in the Supabase SQL editor BEFORE db/policies.sql.
-- Safe to re-run: every statement is idempotent.
--
-- WHY TEXT PRIMARY KEYS, NOT UUIDS
--   The domain models already mint their own prefixed ids ("as_ab12cd34",
--   "sub_9f21c003"). Those ids are readable, they are what the pages pass
--   around, and the existing tests assert on them. Converting to uuid would
--   mean rewriting the models to gain nothing the app can use, so the database
--   stores the ids the application already has.
--
-- WHY QUESTIONS AND ANSWERS ARE THEIR OWN TABLES
--   In session state a Question is nested inside an Assessment, and answers are
--   a dict on a Submission. Nesting them as jsonb here would have been a
--   smaller diff, but it would make the two things this app is actually built
--   to do awkward to express in SQL: "which topics is this student weak on"
--   and "hide the model answer from students". Both are per-question. So
--   questions and answers are rows.

begin;

-- ---------------------------------------------------------------------------
-- profiles: the bridge between Supabase Auth and the app's User model
-- ---------------------------------------------------------------------------
-- auth.users is owned by Supabase and cannot be extended. A profile carries the
-- application id and, critically, the ROLE. The role lives here - server side,
-- writable only by a service role - because the whole point of leaving demo
-- mode is that a user can no longer declare themselves a teacher.
create table if not exists public.profiles (
    id            text primary key,
    auth_user_id  uuid unique references auth.users (id) on delete cascade,
    display_name  text not null check (length(trim(display_name)) between 1 and 60),
    role          text not null default 'student' check (role in ('student', 'teacher')),
    -- Which teacher's roster a student sits on. Null for teachers.
    teacher_id    text references public.profiles (id) on delete set null,
    year_group    integer check (year_group between 7 and 11),
    created_at    timestamptz not null default now(),

    -- A teacher cannot sit on another teacher's roster.
    constraint teacher_has_no_roster check (role = 'student' or teacher_id is null)
);

create index if not exists profiles_teacher_id_idx on public.profiles (teacher_id);
create index if not exists profiles_auth_user_id_idx on public.profiles (auth_user_id);

-- ---------------------------------------------------------------------------
-- assessments
-- ---------------------------------------------------------------------------
create table if not exists public.assessments (
    id              text primary key,
    title           text not null check (length(trim(title)) > 0),
    subject         text not null default 'Mathematics',
    curriculum      text not null default 'Cambridge IGCSE',
    grade_level     integer not null check (grade_level between 7 and 11),
    topic           text not null check (length(trim(topic)) > 0),
    assessment_type text not null default 'homework'
                    check (assessment_type in ('homework', 'exercise', 'mock_exam', 'exam')),
    -- Derived from the questions by the application; mirrored here so listings
    -- do not have to aggregate. Kept honest by the trigger at the bottom.
    max_marks       numeric(6, 2) not null default 0 check (max_marks >= 0),
    created_at      timestamptz not null default now(),

    -- Null for the seeded demo set, which belongs to nobody.
    owner_id        text references public.profiles (id) on delete cascade,
    student_created boolean not null default false,

    -- Shared into the public library, where any student can take a copy.
    -- Private by default: sharing is always a deliberate act by the owner.
    is_shared       boolean not null default false,

    -- Set when this set was copied out of the library. `on delete set null`
    -- so deleting an original never removes anybody's working copy.
    copied_from_id  text references public.assessments (id) on delete set null
);

create index if not exists assessments_owner_id_idx on public.assessments (owner_id);
create index if not exists assessments_topic_idx on public.assessments (topic);
-- The library listing filters on both columns together.
create index if not exists assessments_shared_idx
    on public.assessments (is_shared, student_created);

-- ---------------------------------------------------------------------------
-- questions
-- ---------------------------------------------------------------------------
-- model_answer is empty-by-default rather than NOT NULL-with-content: a student
-- typing up their own worksheet has the questions and nothing else, and that
-- set is still worth saving. Assessment.is_gradable is what gates marking.
create table if not exists public.questions (
    id               text primary key,
    assessment_id    text not null references public.assessments (id) on delete cascade,
    -- Preserves the order the questions were authored in. Rows have no order.
    position         integer not null check (position >= 0),
    question_text    text not null check (length(trim(question_text)) > 0),
    model_answer     text not null default '',
    marking_criteria text not null default '',
    max_marks        numeric(6, 2) not null check (max_marks > 0 and max_marks <= 100),

    unique (assessment_id, position)
);

create index if not exists questions_assessment_id_idx on public.questions (assessment_id);

-- ---------------------------------------------------------------------------
-- submissions
-- ---------------------------------------------------------------------------
create table if not exists public.submissions (
    id                    text primary key,
    assessment_id         text not null references public.assessments (id) on delete cascade,
    -- The anonymous code shown in the UI ("S-1102"), never a real name.
    student_identifier    text not null check (length(trim(student_identifier)) between 1 and 40),
    submission_text       text not null check (length(trim(submission_text)) > 0),
    uploaded_filename     text,
    submitted_at          timestamptz not null default now(),
    status                text not null default 'pending'
                          check (status in ('pending', 'graded', 'reviewed')),
    student_id            text references public.profiles (id) on delete cascade,
    is_self_study         boolean not null default false,
    -- The mark the teacher actually wrote on the paper, when the student knows
    -- it. Divergence from the AI estimate is what raises a marking mismatch.
    teacher_awarded_score numeric(6, 2) check (teacher_awarded_score >= 0)
);

create index if not exists submissions_assessment_id_idx on public.submissions (assessment_id);
create index if not exists submissions_student_id_idx on public.submissions (student_id);

-- ---------------------------------------------------------------------------
-- submission_answers: one answer per question
-- ---------------------------------------------------------------------------
-- A blank answer_text is meaningful and is kept: "left this one blank" is real
-- evidence about a topic. A MISSING row means the question was never attempted.
-- The application relies on that distinction (Submission.answer_for).
create table if not exists public.submission_answers (
    submission_id text not null references public.submissions (id) on delete cascade,
    question_id   text not null references public.questions (id) on delete cascade,
    answer_text   text not null default '',

    primary key (submission_id, question_id)
);

-- ---------------------------------------------------------------------------
-- grading_results
-- ---------------------------------------------------------------------------
-- One row per question per submission. Every row is a RECOMMENDATION until a
-- teacher settles it; see review_status, and final_score in the model.
create table if not exists public.grading_results (
    submission_id             text not null references public.submissions (id) on delete cascade,
    question_id               text not null references public.questions (id) on delete cascade,
    max_marks                 numeric(6, 2) not null check (max_marks > 0),
    suggested_score           numeric(6, 2) not null check (suggested_score >= 0),
    confidence                numeric(4, 3) not null check (confidence between 0 and 1),
    correct_elements          text[] not null default '{}',
    -- [{"error_type": "arithmetic_error", "explanation": "..."}, ...]
    errors                    jsonb not null default '[]'::jsonb,
    student_feedback          text not null default '',
    teacher_note              text not null default '',
    review_status             text not null default 'awaiting_review'
                              check (review_status in ('awaiting_review', 'approved', 'edited', 'flagged')),
    teacher_approved_score    numeric(6, 2) check (teacher_approved_score >= 0),
    teacher_approved_feedback text,
    graded_at                 timestamptz not null default now(),

    primary key (submission_id, question_id),

    -- The same bounds the pydantic model enforces. Stated twice on purpose: a
    -- score above the maximum must be impossible to write even if something
    -- other than this application ever talks to the database.
    constraint suggested_within_max check (suggested_score <= max_marks),
    constraint approved_within_max
        check (teacher_approved_score is null or teacher_approved_score <= max_marks)
);

create index if not exists grading_results_review_status_idx
    on public.grading_results (review_status);

-- ---------------------------------------------------------------------------
-- study_camps and study_sessions
-- ---------------------------------------------------------------------------
-- baseline_percentage is written once at creation and never recalculated: the
-- improvement story ("started at 60%, now at 90%") is only honest if the
-- starting point cannot move. db/policies.sql forbids updating it.
create table if not exists public.study_camps (
    id                  text primary key,
    student_id          text not null references public.profiles (id) on delete cascade,
    topics              text[] not null default '{}',
    started_on          date not null default current_date,
    duration_days       integer not null check (duration_days between 1 and 14),
    baseline_percentage numeric(5, 2) not null check (baseline_percentage between 0 and 100),
    created_at          timestamptz not null default now()
);

create index if not exists study_camps_student_id_idx on public.study_camps (student_id);

create table if not exists public.study_sessions (
    camp_id      text not null references public.study_camps (id) on delete cascade,
    day          integer not null check (day >= 1),
    topic        text not null,
    questions    text[] not null default '{}',
    method_hints text[] not null default '{}',
    skill_focus  text not null default '',
    completed    boolean not null default false,
    -- Questions answered correctly, self-reported. Null until completed.
    score        integer check (score >= 0),

    primary key (camp_id, day),

    -- A score cannot exceed the number of questions in the session.
    constraint score_within_question_count
        check (score is null or score <= cardinality(questions))
);

-- ---------------------------------------------------------------------------
-- Keep assessments.max_marks derived from the questions
-- ---------------------------------------------------------------------------
-- The pydantic model already does this on the way in. The trigger means the
-- column cannot drift if a question is edited or deleted by anything else.
create or replace function public.sync_assessment_max_marks()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
declare
    target_id text := coalesce(new.assessment_id, old.assessment_id);
begin
    update public.assessments a
       set max_marks = coalesce(
               (select round(sum(q.max_marks), 2)
                  from public.questions q
                 where q.assessment_id = target_id),
               0)
     where a.id = target_id;
    return null;
end;
$fn$;

drop trigger if exists questions_sync_max_marks on public.questions;
create trigger questions_sync_max_marks
    after insert or update of max_marks, assessment_id or delete
    on public.questions
    for each row
    execute function public.sync_assessment_max_marks();

commit;
