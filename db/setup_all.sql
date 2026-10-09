-- Camp Prep AI: all-in-one Supabase setup and repair.
-- Run the ENTIRE file in the Supabase SQL Editor for this app's project.
-- Includes schema, migrations 001-008, final policies and API cache reload.
-- Generated from the current repository SQL files on 2026-10-09.
-- Existing app rows and account roles are preserved; repeat runs are supported.
-- One transaction: any failing statement prevents the setup from committing.
-- Do not add API keys or passwords to this script.

begin;

-- Upgrade the library column before schema.sql creates its index on older databases.
alter table if exists public.assessments
    add column if not exists is_shared boolean not null default false;

-- Source: db/schema.sql
create table if not exists public.profiles (
    id            text primary key,
    auth_user_id  uuid unique references auth.users (id) on delete cascade,
    display_name  text not null check (length(trim(display_name)) between 1 and 60),
    role          text not null default 'student' check (role in ('student', 'teacher')),
    teacher_id    text references public.profiles (id) on delete set null,
    year_group    integer check (year_group between 7 and 11),
    avatar_url    text,
    created_at    timestamptz not null default now(),

    constraint teacher_has_no_roster check (role = 'student' or teacher_id is null)
);

create index if not exists profiles_teacher_id_idx on public.profiles (teacher_id);
create index if not exists profiles_auth_user_id_idx on public.profiles (auth_user_id);

create table if not exists public.assessments (
    id              text primary key,
    title           text not null check (length(trim(title)) > 0),
    subject         text not null default 'Mathematics',
    curriculum      text not null default 'Cambridge IGCSE',
    grade_level     integer not null check (grade_level between 7 and 11),
    topic           text not null check (length(trim(topic)) > 0),
    assessment_type text not null default 'homework'
                    check (assessment_type in ('homework', 'exercise', 'mock_exam', 'exam')),
    max_marks       numeric(6, 2) not null default 0 check (max_marks >= 0),
    created_at      timestamptz not null default now(),

    owner_id        text references public.profiles (id) on delete set null,
    student_created boolean not null default false,

    is_shared       boolean not null default false,
    is_archived     boolean not null default false,

    copied_from_id  text references public.assessments (id) on delete set null
);

create index if not exists assessments_owner_id_idx on public.assessments (owner_id);
create index if not exists assessments_topic_idx on public.assessments (topic);
create index if not exists assessments_shared_idx
    on public.assessments (is_shared, student_created);

create table if not exists public.questions (
    id               text primary key,
    assessment_id    text not null references public.assessments (id) on delete cascade,
    position         integer not null check (position >= 0),
    question_text    text not null check (length(trim(question_text)) > 0),
    model_answer     text not null default '',
    marking_criteria text not null default '',
    max_marks        numeric(6, 2) not null check (max_marks > 0 and max_marks <= 100),

    unique (assessment_id, position)
);

create index if not exists questions_assessment_id_idx on public.questions (assessment_id);

create table if not exists public.submissions (
    id                    text primary key,
    assessment_id         text not null references public.assessments (id) on delete cascade,
    student_identifier    text not null check (length(trim(student_identifier)) between 1 and 40),
    submission_text       text not null check (length(trim(submission_text)) > 0),
    uploaded_filename     text,
    submitted_at          timestamptz not null default now(),
    status                text not null default 'pending'
                          check (status in ('pending', 'graded', 'reviewed')),
    student_id            text references public.profiles (id) on delete cascade,
    is_self_study         boolean not null default false,
    teacher_awarded_score numeric(6, 2) check (teacher_awarded_score >= 0),
    attempt_number        integer not null default 1 check (attempt_number >= 1)
);

create index if not exists submissions_assessment_id_idx on public.submissions (assessment_id);
create index if not exists submissions_student_id_idx on public.submissions (student_id);

create table if not exists public.submission_answers (
    submission_id text not null references public.submissions (id) on delete cascade,
    question_id   text not null references public.questions (id) on delete cascade,
    answer_text   text not null default '',

    primary key (submission_id, question_id)
);

create table if not exists public.grading_results (
    submission_id             text not null references public.submissions (id) on delete cascade,
    question_id               text not null references public.questions (id) on delete cascade,
    max_marks                 numeric(6, 2) not null check (max_marks > 0),
    suggested_score           numeric(6, 2) not null check (suggested_score >= 0),
    confidence                numeric(4, 3) not null check (confidence between 0 and 1),
    correct_elements          text[] not null default '{}',
    errors                    jsonb not null default '[]'::jsonb,
    student_feedback          text not null default '',
    teacher_note              text not null default '',
    review_status             text not null default 'awaiting_review'
                              check (review_status in ('awaiting_review', 'approved', 'edited', 'flagged')),
    teacher_approved_score    numeric(6, 2) check (teacher_approved_score >= 0),
    teacher_approved_feedback text,
    graded_at                 timestamptz not null default now(),

    primary key (submission_id, question_id),

    constraint suggested_within_max check (suggested_score <= max_marks),
    constraint approved_within_max
        check (teacher_approved_score is null or teacher_approved_score <= max_marks)
);

create index if not exists grading_results_review_status_idx
    on public.grading_results (review_status);

create table if not exists public.study_camps (
    id                  text primary key,
    student_id          text not null references public.profiles (id) on delete cascade,
    topics              text[] not null default '{}',
    started_on          date not null default current_date,
    duration_days       integer not null check (duration_days between 1 and 14),
    baseline_percentage numeric(5, 2) check (baseline_percentage between 0 and 100),
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
    score        integer check (score >= 0),

    primary key (camp_id, day),

    constraint score_within_question_count
        check (score is null or score <= cardinality(questions))
);

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
revoke all on function public.sync_assessment_max_marks() from public, anon;

drop trigger if exists questions_sync_max_marks on public.questions;
create trigger questions_sync_max_marks
    after insert or update of max_marks, assessment_id or delete
    on public.questions
    for each row
    execute function public.sync_assessment_max_marks();

-- Source: db/migrations/001_shared_library.sql
alter table public.assessments
    add column if not exists is_shared boolean not null default false;

alter table public.assessments
    add column if not exists copied_from_id text
        references public.assessments (id) on delete set null;

create index if not exists assessments_shared_idx
    on public.assessments (is_shared, student_created);

-- Source: db/migrations/002_auth_profiles.sql
create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
declare
    new_profile_id text := 'usr_' || substr(replace(new.id::text, '-', ''), 1, 12);
    anonymous_code text := 'S-' || lpad(
        (abs(hashtext(new.id::text)) % 9000 + 1000)::text, 4, '0');
begin
    insert into public.profiles (id, auth_user_id, display_name, role)
    values (new_profile_id, new.id, anonymous_code, 'student')
    on conflict (auth_user_id) do nothing;

    return new;
end;
$fn$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row
    execute function public.handle_new_auth_user();

-- Install policy helpers before the roster and review migrations use them.
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

revoke all on function public.app_profile_id() from public, anon;
grant execute on function public.app_profile_id() to authenticated;

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

revoke all on function public.app_is_teacher() from public, anon;
grant execute on function public.app_is_teacher() to authenticated;

create or replace function public.app_my_teacher_id()
returns text
language sql
stable
security definer
set search_path = public
as $fn$
    select teacher_id from public.profiles where auth_user_id = auth.uid();
$fn$;

revoke all on function public.app_my_teacher_id() from public, anon;
grant execute on function public.app_my_teacher_id() to authenticated;

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

revoke all on function public.app_teaches(text) from public, anon;
grant execute on function public.app_teaches(text) to authenticated;

create or replace function public.app_submission_finalised(p_submission_id text)
returns boolean
language sql
stable
security definer
set search_path = public
as $fn$
    select exists (
        select 1
          from public.grading_results g
          join public.submissions s on s.id = g.submission_id
         where g.submission_id = p_submission_id
           and s.student_id = public.app_profile_id()
           and g.review_status in ('approved', 'edited', 'flagged')
    );
$fn$;
revoke all on function public.app_submission_finalised(text) from public, anon;
grant execute on function public.app_submission_finalised(text) to authenticated;

-- Source: db/migrations/003_roster.sql
create table if not exists public.class_invites (
    code       text primary key check (code ~ '^[A-HJ-NP-Z2-9]{6}$'),
    teacher_id text not null references public.profiles (id) on delete cascade,
    created_at timestamptz not null default now(),
    revoked    boolean not null default false
);

create index if not exists class_invites_teacher_idx
    on public.class_invites (teacher_id, revoked);

alter table public.class_invites enable row level security;

drop policy if exists class_invites_own on public.class_invites;
create policy class_invites_own on public.class_invites
    for all to authenticated
    using (teacher_id = public.app_profile_id() and public.app_is_teacher())
    with check (teacher_id = public.app_profile_id() and public.app_is_teacher());

create or replace function public.generate_class_code()
returns text
language plpgsql
security definer
set search_path = public
as $fn$
declare
    alphabet constant text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    candidate text;
    attempts  integer := 0;
begin
    loop
        candidate := '';
        for _i in 1..6 loop
            candidate := candidate ||
                substr(alphabet, floor(random() * length(alphabet))::int + 1, 1);
        end loop;

        exit when not exists (
            select 1 from public.class_invites where code = candidate
        );

        attempts := attempts + 1;
        if attempts > 20 then
            raise exception 'Could not generate an unused class code.';
        end if;
    end loop;

    return candidate;
end;
$fn$;

create or replace function public.rotate_class_code()
returns text
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me   text := public.app_profile_id();
    code text;
begin
    if me is null or not public.app_is_teacher() then
        raise exception 'Only a teacher can issue a class code.';
    end if;

    update public.class_invites
       set revoked = true
     where teacher_id = me and not revoked;

    code := public.generate_class_code();
    insert into public.class_invites (code, teacher_id) values (code, me);
    return code;
end;
$fn$;

create or replace function public.join_class(p_code text)
returns text
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me      text := public.app_profile_id();
    my_role text;
    found   text;
begin
    if me is null then
        raise exception 'Not signed in.';
    end if;

    select role into my_role from public.profiles where id = me;
    if my_role <> 'student' then
        raise exception 'Only a student can join a class.';
    end if;

    select teacher_id into found
      from public.class_invites
     where code = upper(trim(p_code)) and not revoked;

    if found is null then
        raise exception 'That class code is not valid.';
    end if;

    update public.profiles set teacher_id = found where id = me;
    return found;
end;
$fn$;

create or replace function public.leave_class()
returns void
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me text := public.app_profile_id();
begin
    if me is null then
        raise exception 'Not signed in.';
    end if;
    update public.profiles set teacher_id = null where id = me;
end;
$fn$;

create or replace function public.remove_from_roster(p_student_id text)
returns boolean
language plpgsql
security definer
set search_path = public
as $fn$
declare
    me text := public.app_profile_id();
begin
    if me is null or not public.app_is_teacher() then
        raise exception 'Only a teacher can change a roster.';
    end if;

    update public.profiles
       set teacher_id = null
     where id = p_student_id and teacher_id = me;

    return found;
end;
$fn$;

revoke execute on function public.generate_class_code() from public, anon;
revoke execute on function public.rotate_class_code() from public, anon;
revoke execute on function public.join_class(text) from public, anon;
revoke execute on function public.leave_class() from public, anon;
revoke execute on function public.remove_from_roster(text) from public, anon;

grant execute on function public.rotate_class_code() to authenticated;
grant execute on function public.join_class(text) to authenticated;
grant execute on function public.leave_class() to authenticated;
grant execute on function public.remove_from_roster(text) to authenticated;

-- Source: db/migrations/004_profile_details.sql
alter table public.profiles add column if not exists avatar_url text;

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
declare
    new_profile_id text := 'usr_' || substr(replace(new.id::text, '-', ''), 1, 12);
    anonymous_code text := 'S-' || lpad(
        (abs(hashtext(new.id::text)) % 9000 + 1000)::text, 4, '0');
    given_name text := left(trim(coalesce(new.raw_user_meta_data ->> 'full_name', '')), 60);
begin
    insert into public.profiles (id, auth_user_id, display_name, role)
    values (
        new_profile_id,
        new.id,
        case when given_name = '' then anonymous_code else given_name end,
        'student'
    )
    on conflict (auth_user_id) do nothing;

    return new;
end;
$fn$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row
    execute function public.handle_new_auth_user();

revoke update on public.profiles from authenticated;
grant update (display_name, year_group, avatar_url) on public.profiles to authenticated;

create or replace function public.delete_my_account()
returns void
language plpgsql
security definer
set search_path = public
as $fn$
begin
    if auth.uid() is null then
        raise exception 'Not signed in';
    end if;
    delete from auth.users where id = auth.uid();
end;
$fn$;

revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('avatars', 'avatars', true, 2097152,
        array['image/png', 'image/jpeg', 'image/webp'])
on conflict (id) do update
    set public = excluded.public,
        file_size_limit = excluded.file_size_limit,
        allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists avatars_insert_own on storage.objects;
create policy avatars_insert_own on storage.objects
    for insert to authenticated
    with check (bucket_id = 'avatars'
                and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists avatars_update_own on storage.objects;
create policy avatars_update_own on storage.objects
    for update to authenticated
    using (bucket_id = 'avatars'
           and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists avatars_delete_own on storage.objects;
create policy avatars_delete_own on storage.objects
    for delete to authenticated
    using (bucket_id = 'avatars'
           and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists avatars_select_own on storage.objects;
create policy avatars_select_own on storage.objects
    for select to authenticated
    using (bucket_id = 'avatars'
           and (storage.foldername(name))[1] = auth.uid()::text);

-- Source: db/migrations/005_teacher_invites.sql
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.teacher_invites (
    id          bigint generated always as identity primary key,
    code_hash   text not null unique,
    note        text,                                  -- who it was for, for the operator
    max_uses    integer not null default 1 check (max_uses >= 1),
    use_count   integer not null default 0 check (use_count >= 0),
    expires_at  timestamptz not null default now() + interval '7 days',
    created_at  timestamptz not null default now(),
    last_used_by text references public.profiles (id) on delete set null,
    last_used_at timestamptz,
    constraint uses_within_limit check (use_count <= max_uses)
);

alter table public.teacher_invites enable row level security;
revoke all on public.teacher_invites from public, anon, authenticated;

create or replace function public.redeem_teacher_invite(code text)
returns void
language plpgsql
security definer
set search_path = public, extensions
as $fn$
declare
    me        text := public.app_profile_id();
    hashed    text;
    invite_id bigint;
begin
    if me is null then
        raise exception 'Not signed in.';
    end if;

    hashed := encode(
        digest(upper(regexp_replace(coalesce(code, ''), '\s', '', 'g')), 'sha256'),
        'hex');

    select id into invite_id
      from public.teacher_invites
     where code_hash = hashed
       and use_count < max_uses
       and expires_at > now()
     for update;

    if invite_id is null then
        raise exception 'That invite code is not valid.';
    end if;

    update public.teacher_invites
       set use_count = use_count + 1,
           last_used_by = me,
           last_used_at = now()
     where id = invite_id;

    update public.profiles
       set role = 'teacher', teacher_id = null
     where id = me;
end;
$fn$;

revoke all on function public.redeem_teacher_invite(text) from public, anon;
grant execute on function public.redeem_teacher_invite(text) to authenticated;

-- Source: db/migrations/006_submission_attempts.sql
alter table public.submissions
    add column if not exists attempt_number integer not null default 1
    check (attempt_number >= 1);

-- Source: db/migrations/007_bug_fixes.sql
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

alter table public.study_camps alter column baseline_percentage drop not null;

-- Source: db/migrations/008_qa_hardening.sql
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
    delete from public.assessments where owner_id = me;
    delete from auth.users where id = auth.uid();
end;
$fn$;
revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.delete_my_account() to authenticated;

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

revoke select on public.grading_results from public, anon, authenticated;
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

-- Source: db/policies.sql
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

revoke all on function public.app_profile_id() from public, anon;
grant execute on function public.app_profile_id() to authenticated;

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

revoke all on function public.app_is_teacher() from public, anon;
grant execute on function public.app_is_teacher() to authenticated;

create or replace function public.app_my_teacher_id()
returns text
language sql
stable
security definer
set search_path = public
as $fn$
    select teacher_id from public.profiles where auth_user_id = auth.uid();
$fn$;

revoke all on function public.app_my_teacher_id() from public, anon;
grant execute on function public.app_my_teacher_id() to authenticated;

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

revoke all on function public.app_teaches(text) from public, anon;
grant execute on function public.app_teaches(text) to authenticated;

create or replace function public.app_submission_finalised(p_submission_id text)
returns boolean
language sql
stable
security definer
set search_path = public
as $fn$
    select exists (
        select 1
          from public.grading_results g
          join public.submissions s on s.id = g.submission_id
         where g.submission_id = p_submission_id
           and s.student_id = public.app_profile_id()
           and g.review_status in ('approved', 'edited', 'flagged')
    );
$fn$;
revoke all on function public.app_submission_finalised(text) from public, anon;
grant execute on function public.app_submission_finalised(text) to authenticated;

alter table public.profiles           enable row level security;
alter table public.assessments        enable row level security;
alter table public.questions          enable row level security;
alter table public.submissions        enable row level security;
alter table public.submission_answers enable row level security;
alter table public.grading_results    enable row level security;
alter table public.study_camps        enable row level security;
alter table public.study_sessions     enable row level security;

drop policy if exists profiles_select_self on public.profiles;
create policy profiles_select_self on public.profiles
    for select to authenticated
    using (auth_user_id = auth.uid() or public.app_teaches(id));

drop policy if exists profiles_update_self on public.profiles;
create policy profiles_update_self on public.profiles
    for update to authenticated
    using (auth_user_id = auth.uid())
    with check (auth_user_id = auth.uid());

revoke update on public.profiles from authenticated;
grant update (display_name, year_group, avatar_url) on public.profiles to authenticated;

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

drop policy if exists questions_select on public.questions;
create policy questions_select on public.questions
    for select to authenticated
    using (
        exists (
            select 1 from public.assessments a
             where a.id = questions.assessment_id
               and (not a.is_archived and (a.owner_id = public.app_profile_id()
                    or public.app_teaches(a.owner_id)
                    or (a.owner_id is null
                        and not a.student_created
                        and public.app_is_teacher())))
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

-- grading_results_insert reads this view, so Postgres refuses to drop the view
-- while the policy exists. Drop it first; it is recreated further down.
drop policy if exists grading_results_insert on public.grading_results;
drop view if exists public.student_questions;
create view public.student_questions as
    select q.id,
           q.assessment_id,
           q.position,
           q.question_text,
           q.max_marks
      from public.questions q
      join public.assessments a on a.id = q.assessment_id
     where (not a.is_archived and a.owner_id = public.app_profile_id())
        or (not a.is_archived and not a.student_created and a.owner_id is null)
        or (not a.is_archived and not a.student_created and a.owner_id = public.app_my_teacher_id())
        or (not a.is_archived and public.app_teaches(a.owner_id))
        or (a.is_shared and a.student_created and not a.is_archived)
        or (a.is_archived and exists (
            select 1 from public.submissions s
             where s.assessment_id = a.id
               and s.student_id = public.app_profile_id()
        ));

grant select on public.student_questions to authenticated;

comment on view public.student_questions is
    'Questions without model answers or marking criteria. The student-facing read path.';

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
        exists (
            select 1 from public.assessments a
             where a.id = submissions.assessment_id and not a.is_archived
        )
        and (student_id = public.app_profile_id()
             or public.app_teaches(student_id))
    );

drop policy if exists submissions_update on public.submissions;
create policy submissions_update on public.submissions
    for update to authenticated
    using (student_id = public.app_profile_id() or public.app_teaches(student_id))
    with check (student_id = public.app_profile_id() or public.app_teaches(student_id));

drop policy if exists submissions_delete_own on public.submissions;
create policy submissions_delete_own on public.submissions
    for delete to authenticated
    using (student_id = public.app_profile_id()
        and not public.app_submission_finalised(id));

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

revoke select on public.grading_results from public, anon, authenticated;
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

-- Check required read views and access grants before committing.
do $verify_setup$
declare
    missing_views text;
begin
    select string_agg(name, ', ' order by name)
      into missing_views
      from (values ('student_questions'), ('student_grading_results'),
                   ('teacher_grading_results')) as expected(name)
     where to_regclass('public.' || name) is null;
    if missing_views is not null then
        raise exception 'Setup incomplete: missing views %', missing_views;
    end if;
    if not has_table_privilege('authenticated', 'public.student_questions', 'SELECT')
       or not has_table_privilege('authenticated', 'public.student_grading_results', 'SELECT')
       or not has_table_privilege('authenticated', 'public.teacher_grading_results', 'SELECT') then
        raise exception 'Setup incomplete: authenticated read-view grants are missing';
    end if;
    if exists (
        select 1 from (values ('profiles'), ('assessments'), ('questions'),
                             ('submissions'), ('submission_answers'), ('grading_results'),
                             ('study_camps'), ('study_sessions'), ('class_invites'),
                             ('teacher_invites'), ('class_join_attempt_windows')) as expected(name)
        left join pg_class c on c.oid = to_regclass('public.' || expected.name)
        where c.oid is null or not c.relrowsecurity
    ) then
        raise exception 'Setup incomplete: an app table is missing or Row Level Security is disabled';
    end if;
end;
$verify_setup$;

-- Delivered after this transaction commits successfully.
notify pgrst, 'reload schema';
commit;

-- Expected: three rows, each marked OK. Then refresh Streamlit and sign in.
select name as component,
       case when to_regclass('public.' || name) is not null
                 and has_table_privilege('authenticated', 'public.' || name, 'SELECT')
            then 'OK' else 'MISSING' end as status
  from (values ('student_questions'), ('student_grading_results'),
               ('teacher_grading_results')) as expected(name)
 order by name;

