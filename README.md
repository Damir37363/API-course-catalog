# course-catalog-api

Backend of the course catalog: FastAPI, SQLAlchemy 2.1, PostgreSQL, and Alembic
migrations (Labs 4–7 of "Advanced Web Technologies").

## How to run

You need Python 3.11 or newer and PostgreSQL 16 or newer.

Once, as the `postgres` superuser, create the role and the database:

```sql
CREATE ROLE catalog_app LOGIN PASSWORD 'change-me';
CREATE DATABASE course_catalog OWNER catalog_app;
```

Then, from the project folder:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
alembic upgrade head               # creates the tables (migrations 0001 and 0002)
psql -h localhost -U catalog_app -d course_catalog -v ON_ERROR_STOP=1 -f seed.sql
alembic check                      # must print: No new upgrade operations detected.
fastapi dev main.py
```

API documentation: http://localhost:8000/docs. The password `change-me` is for
teaching; in a real project, passwords are never put into the repository.

Useful checks (from the project root, with the virtual environment active):

```bash
python check_db.py       # connects to course_catalog
python check_models.py   # the constraint names in the models match the database
python try_errors.py     # with the server running: 5 of 5 as expected
```

Notes:

- The database address comes from `DATABASE_URL` (the environment variable wins over `.env`). `.env` is not in git; `.env.example` is the template. Add `SQL_ECHO=true` to your own `.env` to print every SQL query (it also prints parameter values, so use it only locally).
- `seed.sql` starts with `TRUNCATE ... RESTART IDENTITY`: it returns the training database to the initial data and resets the number counters. Never run it on a working database.
- If the database already exists and its tables were created by hand from `schema.sql` of Lab 6 (without `level`), do not run `alembic upgrade head` straight away: it would try to create existing tables (`DuplicateTable`). Run `alembic stamp 0001`, then `alembic upgrade head` (it adds `level`), then `alembic check`.
- Run Alembic only from the project root (next to `alembic.ini`).

## What changed in the API

- The data now lives in PostgreSQL, not in lists in the program's memory: `data.py` and the `ENROLLMENTS` list are gone. Likes, students, and enrollments survive a server restart (checked: after a restart a course still had the liked number).
- `POST /enrollments` now takes `{"courseId", "studentId"}` instead of `studentName` and answers `201` with `id`, `courseId`, `studentId`, and `enrolledAt`. The enrollment form of the Next.js frontend (Lab 5) still sends `studentName`, so it gets `422` until it is updated; test the API through `/docs`: first create a student (`POST /students`), then an enrollment.
- New routes: `POST /students` (`name`, `email`; answers `201` with the student's `id`) and `GET /stats/courses` (the number of enrollments per course, courses without enrollments show `0`). `GET /enrollments` additionally returns `studentId`, `enrolledAt`, `courseTitle`, and `studentName` (a `JOIN` of three tables).
- Every course has a required `level` field (`beginner` or `intermediate` in the seed data; existing courses got it by a rule: elective courses are `beginner`, the rest `intermediate`). The list route has a new filter `GET /courses?level=beginner`; it combines with `is_elective`, `sort`, and the pages.
- Database constraint violations turn into responses by the constraint name: a duplicate email and a repeated enrollment give `409`, a nonexistent course or student gives `404`, a body that Pydantic rejects gives `422`; a violation that is not in the dictionary stays a `500` (it is a bug in the code, not the client's fault).
- Unchanged: the URLs, the camelCase JSON fields, the CORS settings, and `POST /courses/{course_id}/like`.

## Migrations

| Command | What it does |
|---------|--------------|
| `alembic upgrade head` | applies all the missing migrations |
| `alembic downgrade -1` | rolls back the last migration |
| `alembic current` | shows the version of the database |
| `alembic history` | shows the chain of migrations |
| `alembic revision --autogenerate -m "text"` | writes a draft from models vs. database |
| `alembic check` | reports whether the models and the database have diverged |
| `alembic upgrade 0001:0002 --sql` | prints the SQL of a migration without running it |
| `alembic stamp head` | marks the database as up to date without running migrations |

The chain: `<base> -> 0001 create catalog tables -> 0002 add course level (head)`.

## Experiment log

Each experiment was done one at a time, and the project was returned to its original state afterwards (PostgreSQL 16.15, SQLAlchemy 2.1.8, Alembic 1.20.1).

| # | Experiment | What I saw | Cause | How I fixed it |
|---|------------|------------|-------|----------------|
| 1 | the `uq` template in `naming_convention` changed to `%(table_name)s_%(column_0_name)s_unique` | `check_models.py`: names only in models `enrollments_course_id_unique`, `students_email_unique`; names only in the database `enrollments_course_id_student_id_key`, `students_email_key` | the names SQLAlchemy builds are now different from the ones PostgreSQL chose in Lab 6; the new template also dropped the second column of the pair (`column_0_name` instead of `column_0_N_name`). Alembic and the error dictionary refer to constraints by name, so they would stop matching | restored the template; `check_models.py` prints `none` and `none` again |
| 2 | `min_length` removed from `StudentIn`, name `N` | `500 Internal Server Error`; in the server log `IntegrityError (psycopg.errors.CheckViolation) ... violates check constraint "students_name_check"`, `Failing row contains (5, N, n@example.com)` | Pydantic no longer stopped the request, and the database protected the data with its CHECK, but `students_name_check` is not in `CONSTRAINT_ERRORS`, so the route treats it as an unknown violation and raises it: a `500` instead of a `422` | put `Field(min_length=2)` back; `try_errors.py` gives `5 of 5` again |
| 3 | a typo in a constraint name in the dictionary (`students_email_uniq`) | `500`; the log shows `UniqueViolation ... unique constraint "students_email_key"`, `Key (email)=(aigerim@example.com) already exists` | `CONSTRAINT_ERRORS.get(...)` found nothing under the real name `students_email_key`, so a known violation was handled as an unknown one; the dictionary keys must equal the database names exactly | restored the key `students_email_key`; `5 of 5` again |
| 4 | `title` without `NOT NULL` in the database (and, second variant, `varchar(100)` instead of `text`), `alembic check` | exit code 255: `Detected NOT NULL on column 'courses.title'`, `New upgrade operations detected: [('modify_nullable', ...)]`; for the type: `Detected type change from VARCHAR(length=100) to Text()` and `modify_type` | someone changed the database by hand; Alembic compares the models with the real schema (nullability and types) and reports the divergence with a nonzero exit code, which is what makes CI fail | `ALTER TABLE courses ALTER COLUMN title SET NOT NULL;` and `... TYPE text;`; `alembic check` prints `No new upgrade operations detected.` and exits with 0 |
| 5 | automatic migration `0002` on existing data (`add_column` with `nullable=False`) | `Running upgrade 0001 -> 0002`, then `NotNullViolation: column "level" of relation "courses" contains null values`, `[SQL: ALTER TABLE courses ADD COLUMN level TEXT NOT NULL]`; `alembic current` still `0001`, no `level` column | a required column without a default cannot be added to a table that has rows (there is no value for them); Alembic compares schemas, not data, so it did not notice; PostgreSQL rolled the whole migration back | rewrote `upgrade()` in three steps: add the column with `NULL`, `UPDATE` the rows by a rule, then `SET NOT NULL` |
| 6 | `import models` commented out in `env.py` | `alembic revision --autogenerate` printed `Detected removed table 'students'`, `'courses'`, `'enrollments'` and the index `enrollments_student_id_idx`; the file `0003_oops.py` contains `op.drop_table` for all three tables | the models were never imported, so `Base.metadata` was empty and Alembic decided that the three tables of the database are superfluous; applying it would delete all the data | did not run it: deleted `0003_oops.py`, put the import back; `alembic check` is clean |
| 7 | a `phone: Mapped[str \| None]` field in the `Student` model without a migration | `alembic check` exit code 255: `Detected added column 'students.phone'`, `New upgrade operations detected: [('add_column', None, 'students', Column('phone', Text(), ...` | the model got ahead of the database: the typical "changed the model, forgot the migration" mistake, which works on one machine and breaks on another | deleted the line (in real work: `alembic revision --autogenerate` and commit it together with the model); `check` is clean |
| 8 | two migrations from one revision (`0003` and `0004` both after `0002`) | `alembic heads` printed `0003 (head)` and `0004 (head)`; `alembic upgrade head` failed (exit code 255): `Multiple head revisions are present for given argument 'head'` | two branches of the history left the same parent, so the chain has two ends and Alembic does not know which one to apply | `alembic merge heads -m "merge phone and language" --rev-id 0005` gave one head (`history` shows `(branchpoint)` and `(mergepoint)`); the experiment files were deleted, `alembic heads` is `0002 (head)` again |

## Decisions

- **The API response is chosen by the constraint name, not by SQLSTATE, and the error is caught after `commit`.** The code `23503` is the same for two different foreign keys, yet the answers differ ("Course not found" and "Student not found"), and the code of a `RESTRICT` violation depends on the PostgreSQL version (`23001` on 18, `23503` on 16 and 17). The name is set by `naming_convention` and does not depend on the version. Checking in advance with a `SELECT` does not work: between the check and the `INSERT` another request can write the same email, so the check races; `UNIQUE` in the database is the only check that does not race. It is easier to try the operation and handle the error (EAFP), and it also saves a query.
- **A like is `UPDATE courses SET likes = likes + 1`, not "read the number, add one, write it back".** With `course.likes += 1` the ORM reads the value into the program and writes the result; two clients that read the same number both write the same new number, and one like is lost. In `UPDATE ... likes = likes + 1` the database does the addition itself under a row lock, so concurrent likes queue up and none is lost; `RETURNING` hands back the updated row in the same round trip.
- **Migration `0002` is split into three steps.** A required (`NOT NULL`) column without a default cannot be added to a table that already has rows: the database has no value for them (experiment 5). So the column is first added allowing `NULL`, then the existing rows are filled by a rule, and only then `NULL` is forbidden. The rule (elective courses are `beginner`, the rest `intermediate`) is a decision about data that Alembic cannot make for us. All three steps run in one transaction, so a failure in the middle leaves the database at `0001`.

## Migration 0002 self-check

| What to check | Result |
|---------------|--------|
| Goal and steps | Yes. One schema change (a required `level` column) in one migration, written as three explicit steps. |
| Data | Yes. `NULL` allowed, then `UPDATE ... CASE WHEN is_elective THEN 'beginner' ELSE 'intermediate' END`, then `SET NOT NULL`; all six existing rows got a value (checked with a `SELECT`). |
| Renames and drops | Yes. It is a pure addition, no rename and no drop in `upgrade()`; the only dropped data would be the new column itself in `downgrade()`. |
| Rollback | Yes. `downgrade()` drops the column; `downgrade -1` really removed it (`column "level" does not exist`) and `upgrade head` created and filled it again. This is acceptable only because the values come from a rule; levels set by hand would be lost, so on a production database a rollback needs a backup. |
| Verification | Yes. The SQL from `alembic upgrade 0001:0002 --sql` was read (`BEGIN`, `ADD COLUMN`, `UPDATE`, `SET NOT NULL`, `UPDATE alembic_version`, `COMMIT`); the `upgrade -> downgrade -> upgrade` cycle passed (on the training database, not on a copy of it); `alembic check` is clean. |
| History | Yes. `alembic heads` shows a single head (`0002`); the migration is in the same commit as the model, the schema, the `level` filter, and `seed.sql`. |
| Application | Yes. Every course response has a new required `level` field and `GET /courses` has the `?level=` filter; `CourseOut` and `seed.sql` were updated. Clients that ignore unknown fields (like the current frontend) are not affected. |

## Bonus

All bonus tasks were done on clean data (`seed.sql`). After tasks 1, 2, and 5 the changes to the models and the migrations were rolled back (`alembic check` is clean, `alembic heads` is `0002`). The scripts of tasks 3–5 stay in the repository: `try_n_plus_1.py`, `try_lost_update.py` (add `atomic` for the fixed variant), and `try_delete.py`.

### Task 1. A CHECK that autogenerate does not see

- I added `CheckConstraint("level IN ('beginner', 'intermediate', 'advanced')", name="level")` to `Course.__table_args__`. `alembic check` still printed `No new upgrade operations detected.`, and `alembic revision --autogenerate` created an empty migration (`pass` in both functions).
- Why: autogenerate compares tables, columns (types, NULL / NOT NULL), indexes, named UNIQUE constraints, and foreign keys. By default it does not compare CHECK constraints (nor `server_default`), so a change to a CHECK never shows up as a difference and has to be written by hand.
- I wrote `0003_level_check.py` by hand: `op.create_check_constraint(op.f("courses_level_check"), "courses", "level IN (...)")` in `upgrade()` and `op.drop_constraint(..., type_="check")` in `downgrade()`. After `alembic upgrade head` the database rejected `UPDATE courses SET level = 'expert'` (`new row for relation "courses" violates check constraint "courses_level_check"`).
- Why `op.f` is needed: Alembic passes every constraint name that is not wrapped in `op.f(...)` through `naming_convention`. The `ck` template is `%(table_name)s_%(constraint_name)s_check`, so the plain string `"courses_level_check"` in `downgrade()` turned into `courses_courses_level_check_check`, a constraint that does not exist. `alembic downgrade -1` failed with `UndefinedObject ... DROP CONSTRAINT courses_courses_level_check_check`, and the database stayed at `0003 (head)`. `op.f("courses_level_check")` means "this name is already final, do not apply the template again"; with it in `downgrade()` the rollback worked (`Running downgrade 0003 -> 0002`). In a project with a `naming_convention`, every constraint name in a migration is wrapped in `op.f(...)`.
- Rolled back: the file `0003_level_check.py` and the `CheckConstraint` line in the model were deleted.

### Task 2. Renaming a column without losing data

- On a throwaway database `scratch` (tables from `alembic upgrade head`, data from `seed.sql`) I renamed `description` to `summary` in the model. Autogenerate saw two independent events, `Detected added column 'courses.summary'` and `Detected removed column 'courses.description'`, and proposed `op.add_column('courses', sa.Column('summary', sa.Text(), nullable=False))` plus `op.drop_column('courses', 'description')`. That would drop every description, and adding a required column to a table that has rows fails.
- `op.alter_column("courses", "description", new_column_name="summary")` is a real rename: the database renames the column in place (an `ALTER TABLE ... RENAME` that only changes the catalog), so the values stay where they were; `downgrade()` does the same in the opposite direction. After `alembic upgrade head` the descriptions were under the new name (for example `api-design | Comparing REST and GraphQL in one hands-on project.`), and `alembic check` printed `No new upgrade operations detected.`
- Cleaned up: the migration file was deleted, the model got `description` back, `DATABASE_URL` was unset, and `scratch` was dropped.

### Task 3. The N+1 problem

`python try_n_plus_1.py` counts the queries with the `before_cursor_execute` event:

```text
lazy          enrollments: 6, queries: 7
selectinload  enrollments: 6, queries: 2
```

- With the default lazy loading, the list of six courses is one query, and each `course.enrollments` access sends one more (`... WHERE enrollments.course_id = ...`): 1 + 6 = 7 queries. With `selectinload` there are two: the list of courses and one shared query for all their enrollments (`WHERE course_id IN (...)`). With six courses the difference is invisible; with six hundred it separates a fast response from a slow one.
- How to notice N+1: turn on `SQL_ECHO=true`, make one API request, and look for identical `SELECT` queries that differ only in a parameter; if their number grows with the number of rows, it is N+1.
- `selectinload` and `joinedload`: `selectinload` runs a separate second query with `IN (...)`, so a collection costs two queries and parent rows are not repeated; it is a good default for collections. `joinedload` does everything in one query with a `LEFT OUTER JOIN`, which suits many-to-one relationships (an enrollment's course), but over a collection it repeats the parent row for every child and requires `.unique()` on the result. `raiseload` turns a hidden lazy query into an error, which helps to catch N+1 in tests. (Only `lazy` and `selectinload` were run here; the `joinedload` comparison is from Lecture 7.)
