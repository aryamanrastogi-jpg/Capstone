-- 008 - close verified QA findings without discarding student work.
-- Run after 001-007. db/policies.sql contains the matching policy definitions
-- for fresh installs.
begin;

-- Keep a teacher's assessment history when their account is deleted. Archived
-- sets are visible only to students who already submitted work to that set.
alter table public.assessments
    add column if not exists is_archived boolean not null default false;
alter table public.assessments
    drop constraint if exists assessments_owner_id_fkey;
alter table public.assessments
    add constraint assessments_owner_id_fkey
    foreign key (owner_id) references public.profiles(id) on delete set null;

drop policy if exists assessments_select on public.assessments;
create policy assessments_select on public.assessments
    for select to authenticated
    using (
        (not is_archived and owner_id = public.app_profile_id())
        or (not is_archived and not student_created and owner_id is null)
        or (not is_archived and not student_created and owner_id = public.app_my_teacher_id())
        or (not is_archived and public.app_teaches(owner_id))
        or (not is_archived and is_shared and student_created)
        or (is_archived and exists (
            select 1 from public.submissions s
             where s.assessment_id = assessments.id
               and s.student_id = public.app_profile_id()
        ))
    );

drop policy if exists questions_select on public.questions;
create policy questions_select on public.questions
    for select to authenticated
    using (
        exists (
            select 1 from public.assessments a
             where a.id = questions.assessment_id
               and (not a.is_archived
                    and (a.owner_id = public.app_profile_id()
                    or public.app_teaches(a.owner_id)
                    or (a.owner_id is null and not a.student_created
                        and public.app_is_teacher())))
        )
    );

-- grading_results_insert reads this view, so Postgres refuses to drop the view
-- while the policy exists. Drop it first; it is recreated further down.
drop policy if exists grading_results_insert on public.grading_results;
drop view if exists public.student_questions;
create view public.student_questions as
    select q.id, q.assessment_id, q.position, q.question_text, q.max_marks
      from public.questions q
      join public.assessments a on a.id = q.assessment_id
     where (not a.is_archived and a.owner_id = public.app_profile_id())
        or (not a.is_archived and not a.student_created and a.owner_id is null)
        or (not a.is_archived and not a.student_created
            and a.owner_id = public.app_my_teacher_id())
        or (not a.is_archived and public.app_teaches(a.owner_id))
        or (a.is_shared and a.student_created and not a.is_archived)
        or (a.is_archived and exists (
            select 1 from public.submissions s
             where s.assessment_id = a.id
               and s.student_id = public.app_profile_id()
        ));
grant select on public.student_questions to authenticated;

drop policy if exists submissions_insert_own on public.submissions;
create policy submissions_insert_own on public.submissions
    for insert to authenticated
    with check (
        exists (
            select 1 from public.assessments a
             where a.id = submissions.assessment_id and not a.is_archived
        )
        and (student_id = public.app_profile_id()
             or public.app_teaches(student_id))
    );

create or replace function public.delete_my_account()
returns void
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me text := public.app_profile_id();
    my_role text;
begin
    if auth.uid() is null or me is null then
        raise exception 'Not signed in';
    end if;
    select role into my_role from public.profiles where id = me;
    if my_role = 'teacher' then
        update public.assessments a
           set is_archived = true, owner_id = null
         where a.owner_id = me
           and exists (select 1 from public.submissions s
                        where s.assessment_id = a.id and s.student_id is not null);
    else
        update public.assessments a
           set is_archived = true, owner_id = null
         where a.owner_id = me
           and exists (select 1 from public.submissions s
                        where s.assessment_id = a.id and s.student_id <> me);
    end if;
    -- Unused sets and the deleting student's own sets are removed. Any set
    -- that another student has used stays archived with that student's history.
    delete from public.assessments where owner_id = me;
    delete from auth.users where id = auth.uid();
end;
$fn$;
revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;

-- Students can only create a grading row for a real question in the submitted
-- assessment, with the question's actual maximum marks.
drop policy if exists grading_results_insert on public.grading_results;
create policy grading_results_insert on public.grading_results
    for insert to authenticated
    with check (
        suggested_score <= max_marks
        and exists (
            select 1 from public.submissions s
             where s.id = grading_results.submission_id
               and (s.student_id = public.app_profile_id()
                    or public.app_teaches(s.student_id))
        )
        and (
            public.app_teaches(
                (select s.student_id from public.submissions s
                  where s.id = grading_results.submission_id))
            or (review_status = 'awaiting_review'
                and teacher_approved_score is null
                and teacher_approved_feedback is null
                and exists (
                    select 1 from public.submissions s
                    join public.student_questions q on q.assessment_id = s.assessment_id
                     where s.id = grading_results.submission_id
                       and s.student_id = public.app_profile_id()
                       and q.id = grading_results.question_id
                       and q.max_marks = grading_results.max_marks
                ))
        )
    );

-- Do not allow students to change or delete a submission once a teacher has
-- taken any review action, including flagging it.
create or replace function public.app_submission_finalised(p_submission_id text)
returns boolean
language sql
stable
security definer
set search_path = public
as $fn$
    select exists (
        select 1 from public.grading_results g
        join public.submissions s on s.id = g.submission_id
         where g.submission_id = p_submission_id
           and s.student_id = public.app_profile_id()
           and g.review_status in ('approved', 'edited', 'flagged')
    );
$fn$;
revoke all on function public.app_submission_finalised(text) from public, anon;
grant execute on function public.app_submission_finalised(text) to authenticated;

drop policy if exists submissions_delete_own on public.submissions;
create policy submissions_delete_own on public.submissions
    for delete to authenticated
    using (student_id = public.app_profile_id()
       and not public.app_submission_finalised(id));

-- Keep full diagnostics behind the teacher view. Student rows omit raw error
-- explanations, correct-elements text, and the teacher-only note. Only error
-- categories with a generic prompt are returned for student analytics.
revoke select on public.grading_results from public, anon, authenticated;
-- Column-level read access, not none. Every write to this table is an upsert
-- (INSERT ... ON CONFLICT DO UPDATE), which must read the key columns to find
-- the conflicting row, and RLS checks that existing row against the SELECT
-- policy. With no SELECT privilege at all, teacher approvals and AI-result
-- saves would fail. teacher_note, errors and correct_elements stay ungranted,
-- so a direct read cannot reach them; both roles read those through the views.
grant select (submission_id, question_id, max_marks, suggested_score,
              confidence, student_feedback, review_status,
              teacher_approved_score, teacher_approved_feedback, graded_at)
    on public.grading_results to authenticated;
drop view if exists public.student_grading_results;
create view public.student_grading_results as
    select g.submission_id, g.question_id, g.max_marks, g.suggested_score,
           g.confidence,
           coalesce((
               select jsonb_agg(jsonb_build_object(
                   'error_type', item->>'error_type',
                   'explanation', 'Review this step.'
               ))
                 from jsonb_array_elements(g.errors) as items(item)
           ), '[]'::jsonb) as errors,
           g.student_feedback, g.review_status,
           g.teacher_approved_score, g.teacher_approved_feedback
      from public.grading_results g
      join public.submissions s on s.id = g.submission_id
     where s.student_id = public.app_profile_id()
       and not public.app_is_teacher();
grant select on public.student_grading_results to authenticated;

drop view if exists public.teacher_grading_results;
create view public.teacher_grading_results as
    select g.*
      from public.grading_results g
      join public.submissions s on s.id = g.submission_id
     where public.app_teaches(s.student_id);
grant select on public.teacher_grading_results to authenticated;

-- Small per-account window limits code guessing. Return the same null result
-- for throttled and invalid codes so this cannot become a class-code oracle.
create table if not exists public.class_join_attempt_windows (
    auth_user_id uuid primary key references auth.users(id) on delete cascade,
    window_started_at timestamptz not null,
    attempts integer not null check (attempts >= 1)
);
alter table public.class_join_attempt_windows enable row level security;
revoke all on public.class_join_attempt_windows from public, anon, authenticated;

create or replace function public.join_class(p_code text)
returns text
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me text := public.app_profile_id();
    my_role text;
    found text;
    attempt_count integer;
begin
    if me is null or auth.uid() is null then
        raise exception 'Not signed in.';
    end if;
    insert into public.class_join_attempt_windows(auth_user_id, window_started_at, attempts)
    values (auth.uid(), now(), 1)
    on conflict (auth_user_id) do update
       set window_started_at = case
               when public.class_join_attempt_windows.window_started_at < now() - interval '15 minutes'
               then now() else public.class_join_attempt_windows.window_started_at end,
           attempts = case
               when public.class_join_attempt_windows.window_started_at < now() - interval '15 minutes'
               then 1 else public.class_join_attempt_windows.attempts + 1 end
    returning attempts into attempt_count;
    if attempt_count > 10 then
        return null;
    end if;
    select role into my_role from public.profiles where id = me;
    if my_role <> 'student' then
        raise exception 'Only a student can join a class.';
    end if;
    select teacher_id into found from public.class_invites
     where code = upper(trim(p_code)) and not revoked;
    if found is null then
        return null;
    end if;
    update public.profiles set teacher_id = found where id = me;
    return found;
end;
$fn$;
revoke all on function public.join_class(text) from public, anon;
grant execute on function public.join_class(text) to authenticated;

-- `SECURITY DEFINER` helpers are callable only by signed-in app users where
-- they are needed; trigger handlers remain callable only by their triggers.
revoke all on function public.app_profile_id() from public, anon;
revoke all on function public.app_is_teacher() from public, anon;
revoke all on function public.app_my_teacher_id() from public, anon;
revoke all on function public.app_teaches(text) from public, anon;
grant execute on function public.app_profile_id() to authenticated;
grant execute on function public.app_is_teacher() to authenticated;
grant execute on function public.app_my_teacher_id() to authenticated;
grant execute on function public.app_teaches(text) to authenticated;
revoke all on function public.handle_new_auth_user() from public, anon, authenticated;
revoke all on function public.sync_assessment_max_marks() from public, anon;
revoke all on function public.generate_class_code() from public, anon, authenticated;
revoke all on function public.rotate_class_code() from public, anon;
revoke all on function public.leave_class() from public, anon;
revoke all on function public.remove_from_roster(text) from public, anon;
revoke all on function public.redeem_teacher_invite(text) from public, anon;

commit;
