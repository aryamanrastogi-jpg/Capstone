-- 003 - names at sign-up, profile photos, and deleting your own account
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
-- Run after 002. Safe to re-run.

begin;

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

commit;
