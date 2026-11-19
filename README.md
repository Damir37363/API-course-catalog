# course-catalog-api

Backend of the course catalog: FastAPI, SQLAlchemy 2.1, PostgreSQL, Alembic and
GraphQL on Strawberry as a second entrance (Labs 4–8, "Advanced Web Technologies").

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

REST docs: http://localhost:8000/docs. GraphiQL: http://localhost:8000/graphql.
The password `change-me` is for training; real projects don't commit passwords.

Scripts (with the server running, from the project root; `seed.sql` returns the data to the start):

```bash
python try_errors.py       # REST errors as Problem Details: 5 of 5 as expected
python try_graphql.py      # GraphQL queries, mutations and errors: 8 of 8 as expected
python try_n_plus_1.py     # SQL queries per GraphQL query: 3 and 3
python measure.py          # REST vs GraphQL for the "My courses" screen
python try_protection.py   # six dangerous queries: depth, aliases, limit, id, introspection
python flood_likes.py      # twelve mutations in one request: refused by the alias limit
psql -h localhost -U catalog_app -d course_catalog -f more_students.sql   # 20 students for the N+1 check
python check_db.py && python check_models.py
```

Notes:

- The database address comes from `DATABASE_URL` (the environment variable wins over `.env`). `.env` is not in git; `.env.example` is the template. Add `SQL_ECHO=true` to your own `.env` to print every SQL query (it also prints parameter values, so use it only locally).
- `seed.sql` starts with `TRUNCATE ... RESTART IDENTITY`: it returns the training database to the initial data and resets the number counters. Never run it on a working database.
- If the database already exists and its tables were created by hand from `schema.sql` of Lab 6 (without `level`), do not run `alembic upgrade head` straight away: it would try to create existing tables (`DuplicateTable`). Run `alembic stamp 0001`, then `alembic upgrade head` (it adds `level`), then `alembic check`.
- Run Alembic only from the project root (next to `alembic.ini`).

## What changed in the API

- **REST errors are Problem Details now** (RFC 9457): `Content-Type: application/problem+json` and a body with `type`, `title`, `status`, `detail`, and `instance`. For example, a repeated enrollment gives `409` with `type: https://example.com/problems/already-enrolled`. The rules and their error codes live in `services.py` (`ServiceError`, the constraint-name dictionary); `problem.py` translates a service error and an ordinary `HTTPException` into the document, so a nonexistent address also answers with `application/problem+json`. The `422` answers of FastAPI keep their own list in `detail`, so the Next.js enrollment form still reads them.
- **`/graphql` appeared** (Strawberry, the same database session as REST, one session per request in `Context`). GraphiQL is the same address opened in a browser: it is a development page with a schema browser and autocompletion, while an ordinary client (the Next.js page) sends the same `POST` with `query` and `variables` and no page around it. Queries: `courses`, `course`, `students`, `student`, `enrollments`; mutations: `enroll` and `likeCourse`. A GET request can carry only a query: a mutation over GET is refused with `400`.
- **Mutations answer with `userErrors` for rule errors** (already enrolled, no such course or student): the HTTP status is `200`, `data.enroll.userErrors[0].code` holds a code such as `ALREADY_ENROLLED`, and `enrollment` is `null`. The top-level `errors` list is for everything else: a query that does not match the schema, a failed check, an unexpected exception. A client has to check both places.
- **`X-SQL-Queries` response header** (`counter.py`): the number of SQL queries the server sent to the database while answering this one HTTP request (REST and GraphQL alike). It is a measuring instrument for experiments with N+1, not a feature for clients.
- **Protection** (GraphQL only): query depth is limited to 5 (`QueryDepthLimiter`), a query may have at most 10 aliases (`MaxAliasesLimiter`), `limit` must be 1–100 (`check_limit`), an `id` must be a number (`parse_id`), and unexpected exceptions are replaced by `Unexpected error.` (`MaskErrors`; the real text stays in the server log). The `GRAPHQL_INTROSPECTION` variable (`true` by default, in `.env.example`) turns introspection off when set to `false`.
- **New REST routes** for the "My courses" screen: `GET /students/{id}` and `GET /students/{id}/enrollments` (the enrollments with course titles; both through the shared `enrollment_details()` query). The Next.js frontend has two pages for comparison: `/my-courses-rest` and `/my-courses` (GraphQL).

## Example queries

The "My courses" query (in the GraphiQL Variables panel: `{"id": "2"}`):

```graphql
query MyCourses($id: ID!) {
  student(id: $id) {
    name
    enrollments { id course { title credits level } }
  }
}
```

The `enroll` mutation (Variables: `{"input": {"courseId": "ai-integration", "studentId": "3"}}`) and its answer on a repeated enrollment:

```graphql
mutation Enroll($input: EnrollInput!) {
  enroll(input: $input) {
    enrollment { id }
    userErrors { code message }
  }
}
```

```json
{"data": {"enroll": {"enrollment": null, "userErrors": [{"code": "ALREADY_ENROLLED", "message": "Student is already enrolled in this course"}]}}}
```

The same mistake over REST (`POST /enrollments`) gives `409` with `application/problem+json` and `type: https://example.com/problems/already-enrolled`. A successful enrollment has the same `enrollment { id }` in `data` and an empty `userErrors`.

## REST vs GraphQL comparison

The "My courses" screen of student 2; numbers from `measure.py`, starting data (the byte count depends a little on the time-zone format of `enrolledAt`).

| Criterion | REST | GraphQL | Source |
|-----------|------|---------|--------|
| Requests and rounds per screen | 5 requests in 2 rounds: the student and his enrollments, then one request per course (the codes are known only after round one) | 1 request, 1 round | `measure.py`, step 8 |
| Bytes in the responses | 1130 (full objects, including fields the screen does not show) | 339 (exactly the fields the screen asked for) | `measure.py`, step 8 |
| SQL queries per screen | 5 (one per request) | 3 (one per type through DataLoaders) | `measure.py`, `X-SQL-Queries` |
| SQL growth with more students | each route's SQL is fixed by its author (`GET /enrollments` is one `JOIN` for any number of rows); the screen needs 2 + n requests, n is the student's courses | without loaders 7 and 7 queries on 3 students, 27 and 24 on 20 (N+1); with DataLoaders 3 and 3 on both 3 and 20 students | `try_n_plus_1.py`, experiments 4–5 |
| Error in the query text | an unknown address or a bad parameter gives a real HTTP status (`404`, `422`) | HTTP `200` with `data: null` and `errors` (`Cannot query field 'titel' ... Did you mean 'title'`); a client that checks only `res.ok` does not notice | experiments 1 and 8 |
| Expected rule error (repeated enrollment) | `409`, `application/problem+json`, `type` `.../already-enrolled` | HTTP `200`, `enrollment: null`, `userErrors[0].code = ALREADY_ENROLLED` | steps 1 and 4 |
| HTTP cache | works out of the box for `GET`: the address is the cache key, so browsers, proxies, and CDNs can store answers (`Cache-Control`, `ETag`) | a single `POST /graphql` address: ordinary HTTP caches do not store `POST`, so caching has to be built separately (persisted queries over `GET`, a client cache by object `id`) | lecture section 14 |
| Protection from "expensive" queries | the server fixes what each route returns; the cost is limited by the route and the page size | the client composes the query, so limits are needed: depth 5, 10 aliases, `limit` 1–100; without them 12 `likeCourse` aliases made 24 SQL queries in one request and with them 0 | experiments 6 and 7 |

**Conclusion.** I would leave simple resource screens and public lists on REST: one route is one `GET`, the answer is cacheable, and errors arrive as ordinary HTTP statuses. I would choose GraphQL for "gathering" screens like "My courses": it took 1 request instead of 5 and 339 bytes instead of 1130, and it needs 3 SQL queries instead of 5, because the client names the fields and relations it needs and the server answers in one round. This benefit costs extra work that REST does not need: DataLoaders (without them 7 queries became 27 on 20 students), protection from deep and wide queries, and a client that checks the `errors` field and not only the HTTP status.

## Experiment log

| # | Experiment | What I saw | Cause | How I fixed it |
|---|------------|------------|-------|----------------|
| 1 | a typo in a field name, an argument name in `snake_case` | HTTP `200`, `data: null` and `Cannot query field 'titel' on type 'Course'. Did you mean 'title', 'level', or 'likes'?`; for `courses(is_elective: true)`: `Unknown argument 'is_elective' on field 'Query.courses'. Did you mean 'isElective'?` | GraphQL checks the query against the schema before running it, and an error of the query comes in the `errors` list with status `200` (the HTTP request itself succeeded). Strawberry turns the Python names into camelCase | wrote `title` and `isElective`; REST query parameters stay `is_elective`, GraphQL arguments are `isElective` |
| 2 | `\| None` removed from the `course` query, a nonexistent course | the schema changed to `course(id: ID!): Course!`; `course(id: "nope")` gave `data: null` and `Cannot return null for non-nullable field Query.course.`; in a query with `a` (exists) and `b` (does not) the whole `data` was `null`, `a` was lost too | `!` promises a value; a `null` in a non-null field cannot be returned, so the `null` climbs up to the nearest nullable parent, here the whole `data` | restored `CourseType \| None`: now the same query gives `{"a": {"title": "API Design: REST vs GraphQL"}, "b": null}` |
| 3 | a mutation with the GET method | a query over GET worked (HTTP `200`); `mutation { likeCourse ... }` over GET gave HTTP `400` `mutations are not allowed when using GET`, and the likes stayed 12 | a GET request must be safe: links, prefetching, caches, and crawlers repeat it without asking, so a change through GET could happen by accident | nothing to fix: mutations are sent only with `POST` |
| 4 | `more_students.sql`: 3 and 20 students, the SQL counter | on 3 students the two queries took 7 and 7 SQL queries, after `more_students.sql` (20 students) 27 and 24 | N+1: each relation (`student.enrollments`, `enrollment.course`) was loaded lazily, one `SELECT` per object, so the number of queries grows with the number of rows | the DataLoaders of step 6: 3 and 3 queries on both 3 and 20 students |
| 5 | a DataLoader batch function that doesn't sort rows by key | the `students` query failed: `Received wrong number of results in dataloader, expected: 3, received: 6` (path `students.0.enrollments`); the `enrollments` query did not fail but showed wrong course titles (enrollment 2 showed `Backend Foundations: FastAPI` instead of `AI/LLM Integration`) | the batch function must return exactly one result for each key, in the order of the keys. `IN (...)` returns rows in any order and may skip keys, and my naive function returned a flat list ordered by the database; a wrong length is an error, but a right length with a wrong order is a silent substitution | `git restore graphql_api.py`: the real function groups the rows by the key value and returns the answers in the order of the keys |
| 6 | six dangerous queries without protection and with it | without: depth 6 and 12 aliases returned data; `limit: -1` returned a database error with the SQL text (`LIMIT must not be negative`, `[SQL: SELECT ...]`); id `abc`: `invalid literal for int() with base 10`; a 20-digit id: `NumericValueOutOfRange`; introspection worked; `flood_likes.py`: 12 likes in one request, 24 SQL queries, likes 11 to 23. With: `'Cycle' exceeds maximum operation depth of 5`; `12 aliases found. Allowed: 10` (0 SQL queries, likes unchanged); `limit must be between 1 and 100`; `Invalid ID: 'abc'`; `Unexpected error.` for the 20-digit id; a legitimate query of depth 4 still worked | in GraphQL the client composes the query, so without limits one request multiplies the work, and raw exceptions leak SQL text and parameter values | the `QueryDepthLimiter(5)`, `MaxAliasesLimiter(10)` and `MaskErrors` extensions, plus `check_limit` and `parse_id` for the known mistakes |
| 7 | introspection off, a typo in a field name | with `GRAPHQL_INTROSPECTION=false` the `__schema` query gave `data: null` and `GraphQL introspection has been disabled ...`; normal queries and `try_graphql.py` (8 of 8) worked; but a typo `cours` still answered `Cannot query field 'cours' on type 'Query'. Did you mean 'course' or 'courses'?` | the extension blocks only the introspection fields `__schema` and `__type`; the validation messages of the query still suggest names from the schema, so introspection off is not full secrecy | returned the variable to `true` (the default); it is one layer of protection, not the only one |
| 8 | client failures: a typo, no `errors` check, the API stopped | typo: the page answered `500` and the dev log had `Error [GraphQLRequestError]: Cannot query field 'titel' on type 'Course'. Did you mean 'title', 'level', or 'likes'?`; without the `errors` check: `500` and `TypeError: Cannot destructure property 'student' of '(intermediate value)' as it is null.`; API stopped: `500` and `TypeError: fetch failed`, `[cause]: Error: connect ECONNREFUSED 127.0.0.1:8000`; after the API restart the page was `200` again | GraphQL answers a query error with HTTP `200`, so `res.ok` is true; without checking `errors` the page gets `data: null` and fails far from the real cause. A stopped API is a network failure, a different kind of error | `git restore .`: `gql()` in `lib/graphql.ts` keeps the `errors` check and throws `GraphQLRequestError` |

## Decisions

- **The rules and their errors live in `services.py`; each layer translates the code its own way.** The rule "a student can enroll in a course once" is written once, and a violation becomes a `ServiceError` with a code such as `ALREADY_ENROLLED`. REST turns it into `409` and a Problem Details document, GraphQL into `userErrors`. If both layers checked the rules themselves, they would be duplicated and would drift apart (one layer would answer `409` and the other would forget the check); and the final guarantee is in any case the database constraint caught after `commit`, which does not race.
- **Loaders are created in `Context`, once per request, and the batch function matches rows to keys by value.** A DataLoader remembers the answers by key and uses the request's database session; if it lived for the whole application it would keep stale data from earlier requests (and other users' data) and a session that is already closed. The batch function must return one answer per key in the order of the keys, but `IN (...)` returns rows in any order and may skip keys, so matching by position gives wrong data (experiment 5, where the course titles were silently replaced); matching by the key value does not depend on the order.
- **Protection is two-layered: `check_limit` and `parse_id` for the known mistakes, `MaskErrors` for everything else.** The checks turn an expected client mistake (a negative `limit`, `id: "abc"`) into a clear message the client can act on, instead of a database error with SQL text, as in experiment 6. `MaskErrors` is the net for what nobody foresaw: it replaces any unexpected exception with `Unexpected error.` and keeps the real text only in the server log. Only masking would leave the client with an uninformative message for its own mistakes; only checks would leak SQL as soon as one case is forgotten.

## Bonus (Lab 8)

### Task 1. Validation errors as Problem Details

- Before: a bad `POST /students` (`name: "N"`, `email: "bad"`) answered with the FastAPI default, `application/json` and a `detail` list. Now it answers `422` with `application/problem+json`, `type: https://example.com/problems/validation-error`, `title: Validation failed`, and an `errors` list, one item for every wrong value: `{"in": "body", "field": "name", "detail": "String should have at least 2 characters"}`. Both mistakes of the request come at once, so the client can fix them in one go. `python try_errors.py` shows `validation-error` in its last row (`5 of 5 as expected`).
- Where the list comes from: `RequestValidationError.errors()` is Pydantic's list of dictionaries, one per wrong value, each with `loc` (the path to the value, for example `["body", "name"]`) and `msg`. The handler in `problem.py` turns the first part of `loc` into `in`, the rest (joined with a dot) into `field`, and `msg` into `detail`.
- Why `errors` is an extension: RFC 9457 defines the members `type`, `title`, `status`, `detail`, and `instance`, and explicitly allows extension members for details specific to a kind of problem. A client that knows only the standard understands the document and ignores `errors`; a client that knows it gets the full list. The validation list enriches the format and does not break it.

### Task 2. `createStudent` and one rule for two APIs

- The problem: a name of two spaces passes Pydantic (`min_length=2` counts characters) and `POST /students` answered `201` and created a student with a blank name.
- The fix lives in `services.py`: `create_student` raises `ServiceError("INVALID_NAME", ...)` when `len(name.strip()) < 2`. REST translates the code with a new `PROBLEMS` entry in `problem.py` (`422`, `.../invalid-name`); GraphQL got the `createStudent` mutation (`CreateStudentInput`, `CreateStudentPayload` with `student` and `userErrors`) and needs no translation table, because `userErrors` carry the code as it is.
- Results: `createStudent` with name `N` gave `userErrors[0].code = INVALID_NAME`; with a taken email `EMAIL_TAKEN`; with `Nurlan Abenov` and a new email it created the student (`student { id name }`). REST with two spaces gave `422` `application/problem+json` and `invalid-name`. `try_graphql.py`: `8 of 8 as expected`, `try_errors.py`: `5 of 5 as expected`; the schema has `createStudent(input: CreateStudentInput!): CreateStudentPayload!`.
- Deliberate break: with the `INVALID_NAME` line of `PROBLEMS` commented out, the REST route answered `500 Internal Server Error` (the server log ends with `KeyError: 'INVALID_NAME'`), while the GraphQL mutation still worked as before. Then I put the line back.
- Why the rule is in `services.py`: it is written once and both APIs get it. If it lived in the Pydantic schema of REST, GraphQL would have no such protection (a name of spaces would pass there), and two copies of a rule drift apart.
- To add a new error code: (1) raise `ServiceError(code, message)` in `services.py`; (2) add the code to `PROBLEMS` in `problem.py` (status, `type` slug, title), otherwise REST answers `500` with a `KeyError`; (3) GraphQL needs nothing; (4) add a case to `try_errors.py` and `try_graphql.py`.

### Task 3. A blocking resolver

I measured four simultaneous requests, where the database "thinks" for 0.5 s in each (`SELECT pg_sleep(0.5)`). The experiment files (`blocking_app.py`, `blocking_client.py`) were run outside the repository and are not added to it.

| Variant | Time for 4 requests |
|---------|---------------------|
| REST, `def` route | 0.63 s |
| GraphQL, synchronous resolver (`def slow_sync`) | 2.03 s |
| GraphQL, `async def` + `run_in_threadpool` | 0.52 s |

- Why the REST `def` route does not block: FastAPI runs a `def` route in a thread pool, so while one request waits for the database, the other three wait in other threads and finish together (about 0.5 s).
- Why the synchronous GraphQL resolver does: Strawberry calls a plain `def` resolver on the event loop thread itself, so the 0.5 s wait stops the whole loop, and the four requests queue up one after another (4 × 0.5 s = 2 s).
- The cure is the line `return await run_in_threadpool(pause, info.context.db)` in an `async def` resolver: the blocking call goes to a worker thread, the loop stays free, and the time falls back to about 0.5 s.
- In this project it is almost invisible, because the queries take milliseconds, so four of them in a row add a few milliseconds. It becomes serious with slow queries (hundreds of milliseconds), many simultaneous users, or calls to external services: then every request waits, even those that do not touch the database. One caution for the cure: a single `Session` is not safe to share between fields that run in parallel threads, so a real project gives each parallel call its own session.

## Earlier labs

The parts below were written in Lab 7 and describe the state of the project before GraphQL.

### Lab 7: what changed in the API

- The data now lives in PostgreSQL, not in lists in the program's memory: `data.py` and the `ENROLLMENTS` list are gone. Likes, students, and enrollments survive a server restart (checked: after a restart a course still had the liked number).
- `POST /enrollments` now takes `{"courseId", "studentId"}` instead of `studentName` and answers `201` with `id`, `courseId`, `studentId`, and `enrolledAt`. The enrollment form of the Next.js frontend (Lab 5) still sends `studentName`, so it gets `422` until it is updated; test the API through `/docs`: first create a student (`POST /students`), then an enrollment.
- New routes: `POST /students` (`name`, `email`; answers `201` with the student's `id`) and `GET /stats/courses` (the number of enrollments per course, courses without enrollments show `0`). `GET /enrollments` additionally returns `studentId`, `enrolledAt`, `courseTitle`, and `studentName` (a `JOIN` of three tables).
- Every course has a required `level` field (`beginner` or `intermediate` in the seed data; existing courses got it by a rule: elective courses are `beginner`, the rest `intermediate`). The list route has a new filter `GET /courses?level=beginner`; it combines with `is_elective`, `sort`, and the pages.
- Database constraint violations turn into responses by the constraint name: a duplicate email and a repeated enrollment give `409`, a nonexistent course or student gives `404`, a body that Pydantic rejects gives `422`; a violation that is not in the dictionary stays a `500` (it is a bug in the code, not the client's fault).
- Unchanged: the URLs, the camelCase JSON fields, the CORS settings, and `POST /courses/{course_id}/like`.

### Migrations

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

### Lab 7: experiment log

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

### Lab 7: decisions

- **The API response is chosen by the constraint name, not by SQLSTATE, and the error is caught after `commit`.** The code `23503` is the same for two different foreign keys, yet the answers differ ("Course not found" and "Student not found"), and the code of a `RESTRICT` violation depends on the PostgreSQL version (`23001` on 18, `23503` on 16 and 17). The name is set by `naming_convention` and does not depend on the version. Checking in advance with a `SELECT` does not work: between the check and the `INSERT` another request can write the same email, so the check races; `UNIQUE` in the database is the only check that does not race. It is easier to try the operation and handle the error (EAFP), and it also saves a query.
- **A like is `UPDATE courses SET likes = likes + 1`, not "read the number, add one, write it back".** With `course.likes += 1` the ORM reads the value into the program and writes the result; two clients that read the same number both write the same new number, and one like is lost. In `UPDATE ... likes = likes + 1` the database does the addition itself under a row lock, so concurrent likes queue up and none is lost; `RETURNING` hands back the updated row in the same round trip.
- **Migration `0002` is split into three steps.** A required (`NOT NULL`) column without a default cannot be added to a table that already has rows: the database has no value for them (experiment 5). So the column is first added allowing `NULL`, then the existing rows are filled by a rule, and only then `NULL` is forbidden. The rule (elective courses are `beginner`, the rest `intermediate`) is a decision about data that Alembic cannot make for us. All three steps run in one transaction, so a failure in the middle leaves the database at `0001`.

### Migration 0002 self-check

| What to check | Result |
|---------------|--------|
| Goal and steps | Yes. One schema change (a required `level` column) in one migration, written as three explicit steps. |
| Data | Yes. `NULL` allowed, then `UPDATE ... CASE WHEN is_elective THEN 'beginner' ELSE 'intermediate' END`, then `SET NOT NULL`; all six existing rows got a value (checked with a `SELECT`). |
| Renames and drops | Yes. It is a pure addition, no rename and no drop in `upgrade()`; the only dropped data would be the new column itself in `downgrade()`. |
| Rollback | Yes. `downgrade()` drops the column; `downgrade -1` really removed it (`column "level" does not exist`) and `upgrade head` created and filled it again. This is acceptable only because the values come from a rule; levels set by hand would be lost, so on a production database a rollback needs a backup. |
| Verification | Yes. The SQL from `alembic upgrade 0001:0002 --sql` was read (`BEGIN`, `ADD COLUMN`, `UPDATE`, `SET NOT NULL`, `UPDATE alembic_version`, `COMMIT`); the `upgrade -> downgrade -> upgrade` cycle passed (on the training database, not on a copy of it); `alembic check` is clean. |
| History | Yes. `alembic heads` shows a single head (`0002`); the migration is in the same commit as the model, the schema, the `level` filter, and `seed.sql`. |
| Application | Yes. Every course response has a new required `level` field and `GET /courses` has the `?level=` filter; `CourseOut` and `seed.sql` were updated. Clients that ignore unknown fields (like the current frontend) are not affected. |

### Lab 7: bonus tasks

All bonus tasks were done on clean data (`seed.sql`). After tasks 1, 2, and 5 the changes to the models and the migrations were rolled back (`alembic check` is clean, `alembic heads` is `0002`). The scripts of tasks 3–5 stay in the repository: `try_n_plus_1_orm.py`, `try_lost_update.py` (add `atomic` for the fixed variant), and `try_delete.py`.

#### Task 1. A CHECK that autogenerate does not see

- I added `CheckConstraint("level IN ('beginner', 'intermediate', 'advanced')", name="level")` to `Course.__table_args__`. `alembic check` still printed `No new upgrade operations detected.`, and `alembic revision --autogenerate` created an empty migration (`pass` in both functions).
- Why: autogenerate compares tables, columns (types, NULL / NOT NULL), indexes, named UNIQUE constraints, and foreign keys. By default it does not compare CHECK constraints (nor `server_default`), so a change to a CHECK never shows up as a difference and has to be written by hand.
- I wrote `0003_level_check.py` by hand: `op.create_check_constraint(op.f("courses_level_check"), "courses", "level IN (...)")` in `upgrade()` and `op.drop_constraint(..., type_="check")` in `downgrade()`. After `alembic upgrade head` the database rejected `UPDATE courses SET level = 'expert'` (`new row for relation "courses" violates check constraint "courses_level_check"`).
- Why `op.f` is needed: Alembic passes every constraint name that is not wrapped in `op.f(...)` through `naming_convention`. The `ck` template is `%(table_name)s_%(constraint_name)s_check`, so the plain string `"courses_level_check"` in `downgrade()` turned into `courses_courses_level_check_check`, a constraint that does not exist. `alembic downgrade -1` failed with `UndefinedObject ... DROP CONSTRAINT courses_courses_level_check_check`, and the database stayed at `0003 (head)`. `op.f("courses_level_check")` means "this name is already final, do not apply the template again"; with it in `downgrade()` the rollback worked (`Running downgrade 0003 -> 0002`). In a project with a `naming_convention`, every constraint name in a migration is wrapped in `op.f(...)`.
- Rolled back: the file `0003_level_check.py` and the `CheckConstraint` line in the model were deleted.

#### Task 2. Renaming a column without losing data

- On a throwaway database `scratch` (tables from `alembic upgrade head`, data from `seed.sql`) I renamed `description` to `summary` in the model. Autogenerate saw two independent events, `Detected added column 'courses.summary'` and `Detected removed column 'courses.description'`, and proposed `op.add_column('courses', sa.Column('summary', sa.Text(), nullable=False))` plus `op.drop_column('courses', 'description')`. That would drop every description, and adding a required column to a table that has rows fails.
- `op.alter_column("courses", "description", new_column_name="summary")` is a real rename: the database renames the column in place (an `ALTER TABLE ... RENAME` that only changes the catalog), so the values stay where they were; `downgrade()` does the same in the opposite direction. After `alembic upgrade head` the descriptions were under the new name (for example `api-design | Comparing REST and GraphQL in one hands-on project.`), and `alembic check` printed `No new upgrade operations detected.`
- Cleaned up: the migration file was deleted, the model got `description` back, `DATABASE_URL` was unset, and `scratch` was dropped.

#### Task 3. The N+1 problem

`python try_n_plus_1_orm.py` counts the queries with the `before_cursor_execute` event:

```text
lazy          enrollments: 6, queries: 7
selectinload  enrollments: 6, queries: 2
```

- With the default lazy loading, the list of six courses is one query, and each `course.enrollments` access sends one more (`... WHERE enrollments.course_id = ...`): 1 + 6 = 7 queries. With `selectinload` there are two: the list of courses and one shared query for all their enrollments (`WHERE course_id IN (...)`). With six courses the difference is invisible; with six hundred it separates a fast response from a slow one.
- How to notice N+1: turn on `SQL_ECHO=true`, make one API request, and look for identical `SELECT` queries that differ only in a parameter; if their number grows with the number of rows, it is N+1.
- `selectinload` and `joinedload`: `selectinload` runs a separate second query with `IN (...)`, so a collection costs two queries and parent rows are not repeated; it is a good default for collections. `joinedload` does everything in one query with a `LEFT OUTER JOIN`, which suits many-to-one relationships (an enrollment's course), but over a collection it repeats the parent row for every child and requires `.unique()` on the result. `raiseload` turns a hidden lazy query into an error, which helps to catch N+1 in tests. (Only `lazy` and `selectinload` were run here; the `joinedload` comparison is from Lecture 7.)

#### Task 4. A lost update in the ORM

`python try_lost_update.py` opens two sessions (Alice and Bob) that read the same course and each add one like:

```text
$ python try_lost_update.py            # a.likes += 1, b.likes += 1
Alice reads 11 | Bob reads 11
in the database: 12

$ python try_lost_update.py atomic     # a.likes = Course.likes + 1, b.likes = Course.likes + 1
Alice reads 11 | Bob reads 11
in the database: 13
```

- The first variant loses a like: `a.likes += 1` reads 11 into Python, computes 12 there, and sends `UPDATE ... SET likes = 12`. Bob read the same 11 earlier, so he also sends `SET likes = 12`; the second write overwrites the first with a value that was already stale, so there are two likes but the counter grew by one.
- The second variant sends an expression, `UPDATE courses SET likes = courses.likes + 1`, so the database does the addition itself, using the value that is in the row at that moment. This is where the row lock from Lecture 6 matters: while one transaction is updating a row, a second `UPDATE` of the same row waits until the first one finishes and then works with its result (12), so the second like brings it to 13. That is why the `like` route is written as `update(Course).values(likes=Course.likes + 1)`.

#### Task 5. passive_deletes and the cascade in the database

`python try_delete.py` deletes student 3 (who has one enrollment). Before: 3 students and 6 enrollments.

- Without `passive_deletes=True` in `Student.enrollments` the script failed: `IntegrityError (psycopg.errors.NotNullViolation) null value in column "student_id" of relation "enrollments" violates not-null constraint`, `Failing row contains (6, ai-integration, null, ...)`, `[SQL: UPDATE enrollments SET student_id=... WHERE enrollments.id = ...]`. The ORM does not know about the database's `ON DELETE CASCADE`: before deleting the student it loaded their enrollments and tried to "detach" them by writing `student_id = NULL`, and the required column refused. The transaction was rolled back (still 3 students and 6 enrollments).
- With `passive_deletes=True` the script finished without errors and the counters became 2 students and 5 enrollments: SQLAlchemy sends only `DELETE FROM students ...`, and the database deletes the student's enrollment by the cascade.
- Why they go together: `ON DELETE CASCADE` is a rule of the database, and `passive_deletes=True` tells the ORM "do not load the children and do not touch them, the database is responsible for the deletion". If the foreign key has `ON DELETE CASCADE`, the relationship on the parent side must have `passive_deletes=True`; otherwise the ORM gets ahead of the database and breaks. Data was restored with `seed.sql`, and the model has `passive_deletes=True` back.
