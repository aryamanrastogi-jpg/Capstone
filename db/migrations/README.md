# Migrations

`db/schema.sql` is written with `create table if not exists`. That makes it safe
to run on a fresh project — and useless for changing one that already exists. A
column added to `schema.sql` after you have applied it will never appear in your
database, because the table it belongs to is already there and the statement
does nothing.

So every change to an applied schema gets a numbered file here, and
`schema.sql` is kept in step so a brand-new project still gets everything in one
pass. Both paths have to end up at the same shape.

Run them in order, in the Supabase SQL editor. Each is idempotent.

| File | What it does |
|---|---|
| `001_shared_library.sql` | Adds `is_shared` and `copied_from_id` to `assessments` for the shared question library |
| `002_auth_profiles.sql` | Creates a profile automatically when someone signs up, and pins the role to `student` |
| `003_roster.sql` | Class join codes, and the functions that let a student join a class without `teacher_id` becoming writable |

## Checking what you have applied

```sql
select column_name
  from information_schema.columns
 where table_schema = 'public' and table_name = 'assessments'
 order by ordinal_position;
```
