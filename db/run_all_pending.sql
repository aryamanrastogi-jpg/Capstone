-- Camp Prep AI - every pending database change, in one script
--
-- Generated 2026-10-02 from db/migrations/* and db/policies.sql.
-- Paste the whole file into the Supabase SQL editor and press Run.
--
-- Checked against the live project on 2026-10-02:
--   applied:     002 (sign-up trigger), 003 (class_invites, join_class)
--   NOT applied: 001, 004, 005, 006, 007
-- 002 is left out on purpose: 004 replaces its trigger.
--
-- It runs as ONE transaction. If any statement fails, nothing is changed -
-- fix the error and run the whole file again. Every statement is idempotent,
-- so running it twice is also safe.

begin;


-- ===========================================================================
-- 001 - shared library columns (NOT applied)
-- source: db/migrations/001_shared_library.sql
-- ===========================================================================
-- 001 - shared question library
--
-- Adds the two columns the shared-library feature needs. If you applied
-- db/schema.sql before those columns were added to it, your database does not
-- have them and `create table if not exists` will never give them to you - the
-- table already exists, so the statement does nothing. Hence this file.
--
-- Safe to re-run, and safe to run on a database that already has the columns.


alter table public.assessments
    add column if not exists is_shared boolean not null default false;

-- `on delete set null`: deleting an original must never remove the working
-- copies other students took from it.
alter table public.assessments
    add column if not exists copied_from_id text
        references public.assessments (id) on delete set null;

-- The library listing filters on both columns together.
create index if not exists assessments_shared_idx
    on public.assessments (is_shared, student_created);


-- The matching read rule lives in db/policies.sql (`assessments_select`), which
-- is written with `drop policy if exists` and can simply be re-run.


-- ===========================================================================
-- 003 - class rosters (already applied; re-run is harmless and fills any gaps)
-- source: db/migrations/003_roster.sql
-- ===========================================================================
-- 003 - class rosters
--
-- THE PROBLEM
--   `profiles.teacher_id` decides what a student can see: their teacher's
--   assessments, and the roster a teacher gets oversight of. Until now the only
--   way to set it was an operator running UPDATE by hand.
--
--   It cannot simply be made writable. db/policies.sql grants UPDATE on
--   (display_name, year_group) only, and that is deliberate - a student who
--   could write their own teacher_id could attach themselves to any teacher in
--   the system and read that class's assessments. Equally, a teacher must not
--   be able to write other people's rows to claim students who never agreed.
--
-- THE SHAPE
--   Joining is consensual in both directions, mediated by a code:
--     * a teacher creates a class code and gives it out however they like
--     * a student enters the code, which attaches THEIR OWN row and nobody
--       else's
--   Neither side can act on the other's row directly. Both operations run in
--   `security definer` functions that check the caller first, so the column
--   itself stays unwritable.
--
--   Students cannot read class_invites at all. If they could, they could list
--   every code in the system and join any class - the table is the guest list,
--   not a public directory.
--
-- Safe to re-run.


create table if not exists public.class_invites (
    -- Six characters from an alphabet with no O/0 or I/1, because these get
    -- read aloud in a classroom and written on a whiteboard.
    code       text primary key check (code ~ '^[A-HJ-NP-Z2-9]{6}$'),
    teacher_id text not null references public.profiles (id) on delete cascade,
    created_at timestamptz not null default now(),
    revoked    boolean not null default false
);

create index if not exists class_invites_teacher_idx
    on public.class_invites (teacher_id, revoked);

alter table public.class_invites enable row level security;

-- A teacher sees and manages their own codes. There is no policy for anybody
-- else, so for a student this table does not exist.
drop policy if exists class_invites_own on public.class_invites;
create policy class_invites_own on public.class_invites
    for all to authenticated
    using (teacher_id = public.app_profile_id() and public.app_is_teacher())
    with check (teacher_id = public.app_profile_id() and public.app_is_teacher());

-- ---------------------------------------------------------------------------
-- Generating a code
-- ---------------------------------------------------------------------------
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

        -- Collisions are unlikely but not impossible, and a silent collision
        -- would put a student in the wrong class. Retry rather than assume.
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

-- ---------------------------------------------------------------------------
-- A teacher issues a code
-- ---------------------------------------------------------------------------
-- Rotating revokes every previous code for that teacher. That is the point of
-- rotating: a code that has leaked has to stop working, and leaving the old one
-- live would make the button a decoration.
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

-- ---------------------------------------------------------------------------
-- A student joins
-- ---------------------------------------------------------------------------
-- Returns the teacher's profile id. Raises with a readable message otherwise -
-- the same message for "no such code" and "revoked code", so the function
-- cannot be used to probe which codes exist.
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
        -- A teacher on another teacher's roster would break the
        -- teacher_has_no_roster constraint, and means nothing anyway.
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

-- A student can always leave. Their own work is theirs and is unaffected; what
-- changes is that their teacher stops seeing it, and they stop seeing the
-- class's assessments.
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

-- ---------------------------------------------------------------------------
-- A teacher removes somebody
-- ---------------------------------------------------------------------------
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

-- Anonymous callers have no business here; each function checks the caller, but
-- not being callable at all is a better default.
revoke execute on function public.generate_class_code() from public, anon;
revoke execute on function public.rotate_class_code() from public, anon;
revoke execute on function public.join_class(text) from public, anon;
revoke execute on function public.leave_class() from public, anon;
revoke execute on function public.remove_from_roster(text) from public, anon;

grant execute on function public.rotate_class_code() to authenticated;
grant execute on function public.join_class(text) to authenticated;
grant execute on function public.leave_class() to authenticated;
grant execute on function public.remove_from_roster(text) to authenticated;


-- ===========================================================================
-- 004 - names at sign-up, avatars, delete_my_account (NOT applied)
-- source: db/migrations/004_profile_details.sql
-- ===========================================================================
-- 004 - names at sign-up, profile photos, and deleting your own account
--
-- WHAT CHANGES
--   * Sign-up now asks for a name. The trigger from 002 is replaced so that the
--     name sent in the sign-up metadata becomes the profile's display_name. An
--     account created without one still gets an anonymous S-code.
--   * profiles.avatar_url holds the public URL of a photo in the `avatars`
--     storage bucket. Each user may only write inside a folder named after
--     their own auth id.
--   * delete_my_account() lets a signed-in user delete themselves. It can only
--     ever delete auth.uid(), and the profile goes with it by cascade.
--
-- The role is still never taken from the client: the trigger always writes
-- role='student', and users can update only display_name, year_group and
-- avatar_url.
--
-- Run after 003. Safe to re-run.


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

-- Column grants: the role stays out of reach.
revoke update on public.profiles from authenticated;
grant update (display_name, year_group, avatar_url) on public.profiles to authenticated;

-- A user deletes their own account, and nobody else's.
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

-- Profile photos. Public to read, so the URL can go straight into an <img>.
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


-- ===========================================================================
-- 005 - teacher invite codes (NOT applied)
-- source: db/migrations/005_teacher_invites.sql
-- ===========================================================================
-- 005 - teacher invite codes
--
-- THE PROBLEM THIS SOLVES
--   Until now a teacher existed only because an operator ran an UPDATE by hand
--   (see the notes at the bottom of 002). That keeps the role out of the
--   client's reach, which is the part that matters, but it means the operator
--   has to learn the new teacher's email, find their row and type SQL for every
--   single person.
--
--   The obvious shortcut - a "sign up as a teacher" box - is the one thing that
--   must never exist: whoever ticks it reads the whole class. So the decision
--   stays with the operator, and only the DELIVERY moves: the operator mints a
--   code, hands it to the teacher out of band, and the teacher redeems it for
--   their own account.
--
-- THE SHAPE
--   * teacher_invites stores a SHA-256 hash of each code, never the code. A
--     leaked table dump (or a backup, or a support screenshot) is then not a
--     list of working promotions. The codes are long random strings, so an
--     unsalted hash is enough - there is no dictionary to attack.
--   * Each code has a use limit and an expiry. Defaults: one use, seven days.
--   * Nobody but the operator can read or write the table. RLS is on with no
--     policy at all, so for `authenticated` and `anon` it does not exist.
--   * redeem_teacher_invite(code) is the only path from a code to the role. It
--     acts on auth.uid()'s own profile and nobody else's, and it fails with ONE
--     message for "no such code", "used up" and "expired", so it cannot be used
--     to probe which codes exist or which are still live.
--
-- Run after 003_roster.sql and 004_profile_details.sql. Safe to re-run.


-- digest() lives in pgcrypto. On Supabase it is installed into `extensions`.
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

-- RLS on, no policies: invisible to every client role. The operator works from
-- the SQL editor, which runs as a role that bypasses RLS.
alter table public.teacher_invites enable row level security;
revoke all on public.teacher_invites from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Redeeming a code
-- ---------------------------------------------------------------------------
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

    -- Normalise the way people type: stray spaces and lower case are forgiven.
    hashed := encode(
        digest(upper(regexp_replace(coalesce(code, ''), '\s', '', 'g')), 'sha256'),
        'hex');

    -- `for update` so two people racing for the last use of a code cannot both
    -- get it.
    select id into invite_id
      from public.teacher_invites
     where code_hash = hashed
       and use_count < max_uses
       and expires_at > now()
     for update;

    if invite_id is null then
        -- Identical for unknown, used and expired. Do not split this up.
        raise exception 'That invite code is not valid.';
    end if;

    update public.teacher_invites
       set use_count = use_count + 1,
           last_used_by = me,
           last_used_at = now()
     where id = invite_id;

    -- teacher_id must be cleared in the same statement: a teacher on somebody
    -- else's roster breaks the teacher_has_no_roster constraint.
    update public.profiles
       set role = 'teacher', teacher_id = null
     where id = me;
end;
$fn$;

revoke all on function public.redeem_teacher_invite(text) from public, anon;
grant execute on function public.redeem_teacher_invite(text) to authenticated;


-- ===========================================================================
-- OPERATOR NOTES - run these by hand, from the SQL editor
-- ===========================================================================
--
-- Mint a code. The plain code is shown ONCE, in the result of this query; only
-- its hash is stored, so copy it now and send it to the teacher privately.
-- Change max_uses / the interval to taste (e.g. 5 uses for a department).
--
-- (`as materialized` makes sure the code returned is the one that was hashed:
-- gen_random_bytes must run once, not once per reference.)
--
--     with new_code as materialized (
--         select upper(encode(extensions.gen_random_bytes(9), 'hex')) as code
--     ), stored as (
--         insert into public.teacher_invites (code_hash, note, max_uses, expires_at)
--         select encode(extensions.digest(code, 'sha256'), 'hex'),
--                'Ms Rao, maths', 1, now() + interval '7 days'
--           from new_code
--     )
--     select code from new_code;
--
-- See what is outstanding (hashes only - the codes are not recoverable):
--
--     select id, note, use_count, max_uses, expires_at, last_used_by, last_used_at
--       from public.teacher_invites
--      order by created_at desc;
--
-- Revoke a code before it expires:
--
--     update public.teacher_invites set expires_at = now() where id = <id>;
--
-- Demote a teacher (their students' teacher_id is left pointing at them; clear
-- those first if the class should not follow):
--
--     update public.profiles set role = 'student' where id = 'usr_<profile id>';


-- ===========================================================================
-- 006 - submissions.attempt_number (NOT applied)
-- source: db/migrations/006_submission_attempts.sql
-- ===========================================================================
-- 006 - remember which attempt a submission was
--
-- Submission.attempt_number drives the attempt loop: questions settle, and the
-- next attempt covers only what is left. Without a column for it, every
-- submission reloaded from Supabase came back as attempt 1, so the loop reset
-- on every sign-in.
--
-- Existing rows default to 1, which is what they were already read back as.
-- Safe to re-run.


alter table public.submissions
    add column if not exists attempt_number integer not null default 1
    check (attempt_number >= 1);


-- ===========================================================================
-- db/policies.sql - re-run; now also carries the 007 policies, view and triggers
-- source: db/policies.sql
-- ===========================================================================
-- Camp Prep AI - Phase 2 Row Level Security
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
grant update (display_name, year_group, avatar_url) on public.profiles to authenticated;

-- The one application path to role='teacher' is
-- public.redeem_teacher_invite(code) in db/migrations/005_teacher_invites.sql:
-- a security-definer function that promotes only auth.uid(), and only against
-- an operator-minted, hashed, expiring code. Its table, teacher_invites, has
-- RLS on and no policies here on purpose - no client role can read it. It is
-- not created in this file because it depends on the migration's pgcrypto.

-- ---------------------------------------------------------------------------
-- assessments
-- ---------------------------------------------------------------------------
-- A student sees: their own typed-up sets, plus the teacher-authored sets
-- belonging to the teacher whose roster they are on, plus the unowned seed set,
-- plus anything a student has deliberately shared into the public library.
-- A teacher sees: their own, plus anything their students created.
--
-- Note what the shared clause does NOT do: it grants select only. Update and
-- delete stay owner-only below, so a shared set can be read and copied by
-- anyone but changed by nobody except the person who wrote it.
drop policy if exists assessments_select on public.assessments;
create policy assessments_select on public.assessments
    for select to authenticated
    using (
        owner_id = public.app_profile_id()
        or (not student_created and owner_id is null)
        or (not student_created and owner_id = public.app_my_teacher_id())
        or public.app_teaches(owner_id)
        or (is_shared and student_created)
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
-- Direct reads are for the person who authored the set, for a teacher on sets
-- their students own, and for a teacher on the unowned seed set - not for
-- every teacher on everything (BUG-002, migration 007). A student reads other
-- people's questions through public.student_questions instead, which does not
-- carry the model answer. See "MODEL ANSWERS" at the bottom.
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
        or public.app_teaches(a.owner_id)
        -- Shared library sets, matching assessments_select (BUG-001, 007).
        or (a.is_shared and a.student_created);

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
-- Freezing a student's own submission (BUG-016, migration 007)
-- ---------------------------------------------------------------------------
-- submissions_update and submission_answers_all let a student write their own
-- rows, and Postgres has no column-level RLS. These triggers narrow that for
-- the student only: teacher-uploaded work is read-only to them, everything is
-- frozen once a result is approved or edited, identity columns never change,
-- and only a teacher can make a submission 'reviewed'. The reasoning is in
-- db/migrations/007_bug_fixes.sql.
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


-- ===========================================================================
-- 007 - audit fixes, incl. nullable study_camps.baseline_percentage (NOT applied)
-- source: db/migrations/007_bug_fixes.sql
-- ===========================================================================
-- 007 - fixes from the QA audit (BUG-001, BUG-002, BUG-010, BUG-016)
--
-- Run in the Supabase SQL editor after 001-006 and db/policies.sql.
-- Safe to re-run: every statement is drop-if-exists / create-or-replace.
-- db/policies.sql carries the same final definitions, so a fresh install that
-- runs schema.sql + migrations + policies.sql ends up at the same shape.
--
-- Nothing here changes existing rows: it changes who may read and write what,
-- and lets study_camps.baseline_percentage be NULL (BUG-010).
-- Run this BEFORE deploying the matching app code.


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

-- ---------------------------------------------------------------------------
-- BUG-010: a study camp on topics with no marked work has no baseline.
-- Store that as NULL instead of a misleading 0%.
-- ---------------------------------------------------------------------------
alter table public.study_camps alter column baseline_percentage drop not null;


commit;

-- ===========================================================================
-- Check it worked (run separately afterwards). Every row should say true.
-- ===========================================================================
-- select 'assessments.is_shared' as item, exists (select 1 from information_schema.columns where table_schema='public' and table_name='assessments' and column_name='is_shared') as ok
-- union all select 'profiles.avatar_url', exists (select 1 from information_schema.columns where table_schema='public' and table_name='profiles' and column_name='avatar_url')
-- union all select 'submissions.attempt_number', exists (select 1 from information_schema.columns where table_schema='public' and table_name='submissions' and column_name='attempt_number')
-- union all select 'avatars bucket', exists (select 1 from storage.buckets where id='avatars')
-- union all select 'teacher_invites', to_regclass('public.teacher_invites') is not null
-- union all select 'redeem_teacher_invite()', to_regprocedure('public.redeem_teacher_invite(text)') is not null
-- union all select 'delete_my_account()', to_regprocedure('public.delete_my_account()') is not null
-- union all select 'submission guard trigger', exists (select 1 from pg_trigger where tgname='submissions_guard_student_write')
-- union all select 'camp baseline nullable', (select is_nullable='YES' from information_schema.columns where table_schema='public' and table_name='study_camps' and column_name='baseline_percentage');
