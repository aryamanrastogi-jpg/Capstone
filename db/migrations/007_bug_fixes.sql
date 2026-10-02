-- 007 - access-control fixes from the QA audit (BUG-001, BUG-002, BUG-016)
--
-- Run in the Supabase SQL editor after 001-006 and db/policies.sql.
-- Safe to re-run: every statement is drop-if-exists / create-or-replace.
-- db/policies.sql carries the same final definitions, so a fresh install that
-- runs schema.sql + migrations + policies.sql ends up at the same shape.
--
-- Nothing here touches data; it only changes who may read and write what.

begin;

-- ---------------------------------------------------------------------------
-- BUG-002: teachers could read every question (and model answer) in the
-- database, because questions_select had an unscoped `or app_is_teacher()`.
--
-- Now a direct read of `questions` - the table that carries model_answer and
-- marking_criteria - is allowed for:
--   * the owner of the set (teacher or student),
--   * a teacher, for sets owned by a student on their roster,
--   * a teacher, for the unowned seed set (owner_id is null), which belongs
--     to nobody and has no private answers to protect.
-- Students never read other people's sets here; they use student_questions
-- below (BUG-001), which has no answer columns.
-- ---------------------------------------------------------------------------
drop policy if exists questions_select on public.questions;
create policy questions_select on public.questions
    for select to authenticated
    using (
        exists (
            select 1 from public.assessments a
             where a.id = questions.assessment_id
               and (a.owner_id = public.app_profile_id()
                    or public.app_teaches(a.owner_id)
                    or (a.owner_id is null
                        and not a.student_created
                        and public.app_is_teacher()))
        )
    );

-- ---------------------------------------------------------------------------
-- BUG-001: signed-in students could not load their teacher's sets or shared
-- library sets: questions_select only returned rows for sets they own, so
-- those assessments arrived with zero questions and failed to load.
--
-- The application now reads questions through this view when the signed-in
-- user is a student (services/repository.py, SupabaseRepository._question_rows)
-- and reads `questions` directly only to pick up the answers of sets the
-- student owns. The view gains the shared-library clause so it matches
-- assessments_select; the roster clause (teacher's own sets) was already here.
--
-- The view still has NO model_answer / marking_criteria columns, and is still
-- not security_invoker: it runs as its owner, so the visibility rule is
-- restated in its WHERE clause. `create or replace` keeps the column list
-- identical, so existing grants survive; the grant is repeated anyway.
-- ---------------------------------------------------------------------------
create or replace view public.student_questions as
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
        or public.app_teaches(a.owner_id)
        or (a.is_shared and a.student_created);

grant select on public.student_questions to authenticated;

comment on view public.student_questions is
    'Questions without model answers or marking criteria. The student-facing read path.';

-- ---------------------------------------------------------------------------
-- BUG-016: a student could rewrite their submission after the teacher had
-- approved it - submission_text, status, teacher_awarded_score, even on work
-- the teacher uploaded - because submissions_update allowed a full UPDATE.
--
-- Postgres has no column-level RLS, and the student does legitimately write
-- two things after inserting: the status (pending -> graded once their AI
-- estimate is stored) and their answers. So the rule is a trigger rather than
-- a grant. For the STUDENT (not their teacher, not the service role):
--   * work their teacher uploaded (is_self_study = false) is read-only;
--   * once any result on the submission is finalised (approved or edited by
--     the teacher) the submission and its answers are frozen;
--   * identity columns (id, student_id, assessment_id, is_self_study,
--     attempt_number) never change;
--   * the status can never be set to 'reviewed' - only a teacher's review
--     makes a submission reviewed;
--   * a student can only insert self-study work, and never as 'reviewed'.
-- Teachers are unaffected; RLS still decides whether they may write at all.
-- A student may still delete their own submission (submissions_delete_own).
-- ---------------------------------------------------------------------------
create or replace function public.app_submission_finalised(p_submission_id text)
returns boolean
language sql
stable
security definer
set search_path = public
as $fn$
    select exists (
        select 1 from public.grading_results g
         where g.submission_id = p_submission_id
           and g.review_status in ('approved', 'edited')
    );
$fn$;

create or replace function public.submissions_guard_student_write()
returns trigger
language plpgsql
set search_path = public
as $fn$
declare
    v_me text := public.app_profile_id();
    v_student_id text;
begin
    if tg_op = 'INSERT' then
        v_student_id := new.student_id;
    else
        v_student_id := old.student_id;
    end if;

    -- Only the student writing their own row is restricted here. Teachers,
    -- and the service role / SQL editor (no profile), are left to RLS.
    if v_me is null
       or v_student_id is distinct from v_me
       or public.app_is_teacher() then
        return new;
    end if;

    if tg_op = 'INSERT' then
        if not new.is_self_study or new.status = 'reviewed' then
            raise exception 'Students can only add their own self-study work.'
                using errcode = '42501';
        end if;
        return new;
    end if;

    -- UPDATE by the student themselves.
    if not old.is_self_study then
        raise exception 'Only your teacher can change work they uploaded.'
            using errcode = '42501';
    end if;
    if public.app_submission_finalised(old.id) then
        raise exception 'This work has been reviewed by your teacher and can no longer be changed.'
            using errcode = '42501';
    end if;
    if new.id is distinct from old.id
       or new.student_id is distinct from old.student_id
       or new.assessment_id is distinct from old.assessment_id
       or new.is_self_study is distinct from old.is_self_study
       or new.attempt_number is distinct from old.attempt_number then
        raise exception 'These details of a submission cannot be changed.'
            using errcode = '42501';
    end if;
    if new.status = 'reviewed' and old.status is distinct from 'reviewed' then
        raise exception 'Only a teacher can mark work as reviewed.'
            using errcode = '42501';
    end if;
    return new;
end;
$fn$;

drop trigger if exists submissions_guard_student_write on public.submissions;
create trigger submissions_guard_student_write
    before insert or update on public.submissions
    for each row
    execute function public.submissions_guard_student_write();

-- The answers are part of the submission, so they freeze with it.
create or replace function public.submission_answers_guard_student_write()
returns trigger
language plpgsql
set search_path = public
as $fn$
declare
    v_me text := public.app_profile_id();
    v_submission_id text;
    v_sub public.submissions%rowtype;
begin
    if tg_op = 'DELETE' then
        v_submission_id := old.submission_id;
    else
        v_submission_id := new.submission_id;
    end if;

    select * into v_sub from public.submissions s where s.id = v_submission_id;

    -- No parent row: this is the cascade from deleting the submission itself,
    -- which submissions_delete_own already allowed. Otherwise only the student
    -- writing their own answers is restricted, as above.
    if found
       and v_me is not null
       and v_sub.student_id = v_me
       and not public.app_is_teacher()
       and (not v_sub.is_self_study or public.app_submission_finalised(v_sub.id)) then
        raise exception 'This work can no longer be changed.'
            using errcode = '42501';
    end if;

    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$fn$;

drop trigger if exists submission_answers_guard_student_write on public.submission_answers;
create trigger submission_answers_guard_student_write
    before insert or update or delete on public.submission_answers
    for each row
    execute function public.submission_answers_guard_student_write();

commit;
