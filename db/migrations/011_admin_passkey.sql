-- 011 - the Admin page opens with a passkey, not an account
--
-- THE PROBLEM THIS SOLVES
--   010 tied the Admin page to signed-in accounts listed in `app_admins`. The
--   page now opens with a passkey instead (the ADMIN_PASSKEY Streamlit secret),
--   with nobody signed in. There is then no auth.uid() for the database to
--   check, so after the passkey checks out the app calls the admin functions
--   with the service-role key (SUPABASE_SERVICE_ROLE_KEY).
--
-- THE SHAPE
--   * Every admin function is executable by `service_role` only. `anon` and
--     `authenticated` - every visitor and every signed-in student or teacher -
--     cannot call them at all, and each one also opens with
--     `app_require_admin()`, which raises unless the request is service-role.
--   * `app_admins` and `is_app_admin()` from 010 are dropped.
--   * `admin_list_teachers()` loses its is_admin column, and demoting no longer
--     has a "yourself" to protect: there is no account behind the page.
--   * Invite codes work exactly as in 010: the plain code is returned once and
--     only its SHA-256 hash is kept.
--
--   The trade-off, chosen deliberately: anybody holding ADMIN_PASSKEY has full
--   admin. Keep it long and random, and rotate it if it might have leaked.
--
-- Run after 010_admin.sql. Safe to re-run.

begin;

create extension if not exists pgcrypto with schema extensions;

-- 010 kept admins in a table and checked the signed-in account. Gone: the
-- Admin page no longer has an account behind it. Any rows in app_admins
-- are dropped with the table.
drop function if exists public.is_app_admin();
drop function if exists public.admin_list_teachers();
drop function if exists public.app_require_admin();
drop table if exists public.app_admins;

-- ---------------------------------------------------------------------------
-- The guard
-- ---------------------------------------------------------------------------
-- Raises unless the request was made with the service-role key. PostgREST puts
-- the JWT claims in `request.jwt.claims`; the role claim is `service_role`
-- only for that key. Not callable by any client role.
create or replace function public.app_require_admin()
returns void
language plpgsql
stable
security definer
set search_path = public
as $fn$
begin
    if coalesce(
        nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role',
        ''
    ) <> 'service_role' then
        raise exception 'Admin access required.' using errcode = '42501';
    end if;
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

revoke all on function public.admin_create_teacher_invite(text, integer, integer) from public, anon, authenticated;
grant execute on function public.admin_create_teacher_invite(text, integer, integer) to service_role;

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

revoke all on function public.admin_list_teacher_invites() from public, anon, authenticated;
grant execute on function public.admin_list_teacher_invites() to service_role;

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

revoke all on function public.admin_cancel_teacher_invite(bigint) from public, anon, authenticated;
grant execute on function public.admin_cancel_teacher_invite(bigint) to service_role;

-- ---------------------------------------------------------------------------
-- Teachers
-- ---------------------------------------------------------------------------
create or replace function public.admin_list_teachers()
returns table (
    profile_id     text,
    display_name   text,
    student_count  bigint,
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
               t.created_at
          from public.profiles t
         where t.role = 'teacher'
         order by t.display_name;
end;
$fn$;

revoke all on function public.admin_list_teachers() from public, anon, authenticated;
grant execute on function public.admin_list_teachers() to service_role;

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
begin
    perform public.app_require_admin();

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

revoke all on function public.admin_demote_teacher(text, boolean) from public, anon, authenticated;
grant execute on function public.admin_demote_teacher(text, boolean) to service_role;

commit;

-- ===========================================================================
-- OPERATOR NOTES
-- ===========================================================================
--
-- The Admin page needs two Streamlit secrets (root level, see
-- .streamlit/secrets.toml.example):
--   ADMIN_PASSKEY              - at least 16 characters; the page refuses a
--                                shorter one. Generate it, do not invent it.
--   SUPABASE_SERVICE_ROLE_KEY  - Supabase > Project Settings > API keys.
--                                It bypasses RLS: keep it in secrets only.
--
-- Check the admin functions are closed to clients:
--
--     select p.proname,
--            has_function_privilege('authenticated', p.oid, 'execute') as authenticated,
--            has_function_privilege('anon', p.oid, 'execute') as anon,
--            has_function_privilege('service_role', p.oid, 'execute') as service_role
--       from pg_proc p join pg_namespace n on n.oid = p.pronamespace
--      where n.nspname = 'public' and p.proname like 'admin%';
--
-- Expected: authenticated false, anon false, service_role true.
