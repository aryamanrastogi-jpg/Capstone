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

begin;

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

commit;

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
