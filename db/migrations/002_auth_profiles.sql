-- 002 - profiles are created by the database, not by the client
--
-- THE PROBLEM THIS SOLVES
--   A profile carries the ROLE, and the role decides whether you see the whole
--   class or only your own work. db/policies.sql therefore has no insert policy
--   on profiles at all: if a signed-in user could insert their own row, they
--   could insert it with role='teacher', and every read policy downstream would
--   believe them.
--
--   But somebody has to create the profile, or a new account has no identity in
--   the app. That work belongs to the database: a trigger on auth.users, owned
--   by the definer, which is the one path that can write a profile - and which
--   always writes role='student'.
--
--   Teachers are promoted deliberately, by an operator, with the statement at
--   the bottom of this file. There is no code path anywhere in the application
--   that grants the teacher role.
--
-- Safe to re-run.

begin;

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
    -- Students are identified by an anonymous code, never by name or email.
    -- Anything the client sent as a display name is deliberately ignored: the
    -- sign-up form is not a place to volunteer a real identity, and the privacy
    -- notice on every page promises it is not stored.
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

commit;

-- ===========================================================================
-- OPERATOR NOTES - run these by hand, from the SQL editor
-- ===========================================================================
--
-- Promote somebody to teacher. There is no application code that does this, on
-- purpose: the whole point of moving off the demo dropdown is that the role is
-- not something a user can choose.
--
--     update public.profiles
--        set role = 'teacher', teacher_id = null
--      where auth_user_id = (select id from auth.users where email = 'them@example.com');
--
-- Put a student on a teacher's roster. Until this is done a new student has no
-- teacher, so `assessments_select` shows them only their own question sets and
-- the unowned seed set - which is correct, but looks empty. Roster management
-- is the next piece of work; this is the manual stand-in.
--
--     update public.profiles
--        set teacher_id = 'usr_<the teacher profile id>'
--      where id = 'usr_<the student profile id>';
--
-- See who exists and what they are:
--
--     select p.id, p.display_name, p.role, p.teacher_id, u.email
--       from public.profiles p
--       join auth.users u on u.id = p.auth_user_id
--      order by p.role, p.display_name;
