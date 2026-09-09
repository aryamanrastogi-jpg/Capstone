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

begin;

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

commit;
