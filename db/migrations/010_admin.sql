-- 010 - an in-app Admin page for teacher invites and teachers
--
-- THE PROBLEM THIS SOLVES
--   Migration 005 moved the DELIVERY of teacher access to invite codes, but
--   minting, listing and revoking those codes, and demoting a teacher, still
--   meant pasting SQL into the Supabase editor. This migration lets the same
--   operator do that from an Admin page, without widening who can do it.
--
-- THE SHAPE
--   * Admin is a flag, not a third role. `app_admins` lists the profiles that
--     may use the Admin page. The student/teacher role, and every policy built
--     on it, is untouched.
--   * Nobody can make themselves an admin. `app_admins` has RLS on and no
--     policy, exactly like `teacher_invites`, so no client role can see or
--     change it. The first admin is added by hand (operator notes below).
--   * Every admin action is a security definer function that starts with
--     `app_require_admin()`, which raises unless the caller is on the list.
--     The page decides nothing; it only calls these.
--   * Plain invite codes still exist only in the result of the call that
--     minted them. The table keeps the SHA-256 hash, as in 005.
--   * No email addresses leave the database: teachers are listed by display
--     name and profile id, as everywhere else in the app.
--
-- Run after 005_teacher_invites.sql. Safe to re-run.

begin;

create extension if not exists pgcrypto with schema extensions;

create table if not exists public.app_admins (
    profile_id  text primary key references public.profiles (id) on delete cascade,
    note        text,                                  -- who and why, for the operator
    created_at  timestamptz not null default now()
);

-- RLS on, no policies: invisible to every client role.
alter table public.app_admins enable row level security;
revoke all on public.app_admins from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Who is an admin
-- ---------------------------------------------------------------------------
-- Answers for the caller only, so the app can show or hide the Admin page.
-- It says nothing about anybody else.
create or replace function public.is_app_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $fn$
    select exists (
        select 1 from public.app_admins a
         where a.profile_id = public.app_profile_id());
$fn$;

revoke all on function public.is_app_admin() from public, anon;
grant execute on function public.is_app_admin() to authenticated;

-- The guard every admin function opens with. Returns the caller's profile id.
-- Not callable by any client role: it only runs inside the definer functions.
create or replace function public.app_require_admin()
returns text
language plpgsql
stable
security definer
set search_path = public
as $fn$
declare
    me text := public.app_profile_id();
begin
    if me is null or not exists (
        select 1 from public.app_admins a where a.profile_id = me
    ) then
        raise exception 'Admin access required.' using errcode = '42501';
    end if;
    return me;
end;
$fn$;

revoke all on function public.app_require_admin() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Invite codes
-- ---------------------------------------------------------------------------
-- Mint a code. The plain code is returned once and never stored.
create or replace function public.admin_create_teacher_invite(
    p_note text,
    p_max_uses integer,
    p_valid_days integer
)
returns text
language plpgsql
volatile
security definer
set search_path = public, extensions
as $fn$
declare
    new_code text;
begin
    perform public.app_require_admin();

    if p_max_uses is null or p_max_uses not between 1 and 20 then
        raise exception 'Uses must be between 1 and 20.';
    end if;
    if p_valid_days is null or p_valid_days not between 1 and 30 then
        raise exception 'Days valid must be between 1 and 30.';
    end if;
    if length(coalesce(p_note, '')) > 120 then
        raise exception 'Keep the note under 120 characters.';
    end if;

    -- Same shape as the operator snippet in 005: 18 upper-case hex characters,
    -- which redeem_teacher_invite normalises and hashes identically.
    new_code := upper(encode(extensions.gen_random_bytes(9), 'hex'));

    insert into public.teacher_invites (code_hash, note, max_uses, expires_at)
    values (
        encode(extensions.digest(new_code, 'sha256'), 'hex'),
        nullif(trim(p_note), ''),
        p_max_uses,
        now() + make_interval(days => p_valid_days)
    );

    return new_code;
end;
$fn$;

revoke all on function public.admin_create_teacher_invite(text, integer, integer) from public, anon;
grant execute on function public.admin_create_teacher_invite(text, integer, integer) to authenticated;

-- Every code, newest first. Hashes are never returned.
create or replace function public.admin_list_teacher_invites()
returns table (
    id            bigint,
    note          text,
    max_uses      integer,
    use_count     integer,
    expires_at    timestamptz,
    created_at    timestamptz,
    last_used_by  text,
    last_used_at  timestamptz
)
language plpgsql
stable
security definer
set search_path = public
as $fn$
begin
    perform public.app_require_admin();

    return query
        select i.id, i.note, i.max_uses, i.use_count, i.expires_at, i.created_at,
               p.display_name, i.last_used_at
          from public.teacher_invites i
          left join public.profiles p on p.id = i.last_used_by
         order by i.created_at desc
         limit 200;
end;
$fn$;

revoke all on function public.admin_list_teacher_invites() from public, anon;
grant execute on function public.admin_list_teacher_invites() to authenticated;

-- Cancel a code now. Already-expired codes are left as they are.
create or replace function public.admin_cancel_teacher_invite(p_invite_id bigint)
returns void
language plpgsql
volatile
security definer
set search_path = public
as $fn$
begin
    perform public.app_require_admin();

    update public.teacher_invites i
       set expires_at = least(i.expires_at, now())
     where i.id = p_invite_id;

    if not found then
        raise exception 'No such invite code.';
    end if;
end;
$fn$;

revoke all on function public.admin_cancel_teacher_invite(bigint) from public, anon;
grant execute on function public.admin_cancel_teacher_invite(bigint) to authenticated;

-- ---------------------------------------------------------------------------
-- Teachers
-- ---------------------------------------------------------------------------
create or replace function public.admin_list_teachers()
returns table (
    profile_id     text,
    display_name   text,
    student_count  bigint,
    is_admin       boolean,
    created_at     timestamptz
)
language plpgsql
stable
security definer
set search_path = public
as $fn$
begin
    perform public.app_require_admin();

    return query
        select t.id, t.display_name,
               (select count(*) from public.profiles s
                 where s.teacher_id = t.id and s.role = 'student'),
               exists (select 1 from public.app_admins a where a.profile_id = t.id),
               t.created_at
          from public.profiles t
         where t.role = 'teacher'
         order by t.display_name;
end;
$fn$;

revoke all on function public.admin_list_teachers() from public, anon;
grant execute on function public.admin_list_teachers() to authenticated;

-- Turn a teacher back into a student. With p_release_students the class goes
-- too: their students' teacher_id is cleared so the roster does not follow a
-- non-teacher. Their assessments and the work handed in against them stay.
create or replace function public.admin_demote_teacher(
    p_profile_id text,
    p_release_students boolean
)
returns void
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
    me text := public.app_require_admin();
begin
    if p_profile_id = me then
        raise exception 'You cannot demote yourself.';
    end if;
    if exists (select 1 from public.app_admins a where a.profile_id = p_profile_id) then
        raise exception 'That teacher is an admin. Remove their admin access first.';
    end if;
    if not exists (
        select 1 from public.profiles p
         where p.id = p_profile_id and p.role = 'teacher'
    ) then
        raise exception 'That account is not a teacher.';
    end if;

    if coalesce(p_release_students, false) then
        update public.profiles s
           set teacher_id = null
         where s.teacher_id = p_profile_id;
    end if;

    update public.profiles p
       set role = 'student'
     where p.id = p_profile_id;
end;
$fn$;

revoke all on function public.admin_demote_teacher(text, boolean) from public, anon;
grant execute on function public.admin_demote_teacher(text, boolean) to authenticated;

commit;

-- ===========================================================================
-- OPERATOR NOTES - run these by hand, from the SQL editor
-- ===========================================================================
--
-- Make somebody an admin (the only way; the app cannot do it). They must have
-- signed up first so their profile exists:
--
--     insert into public.app_admins (profile_id, note)
--     select p.id, 'Herdy - operator'
--       from public.profiles p
--       join auth.users u on u.id = p.auth_user_id
--      where u.email = 'them@example.com'
--     on conflict (profile_id) do nothing;
--
-- See who is an admin:
--
--     select a.profile_id, p.display_name, a.note, a.created_at
--       from public.app_admins a join public.profiles p on p.id = a.profile_id;
--
-- Remove admin access:
--
--     delete from public.app_admins where profile_id = 'usr_<profile id>';
