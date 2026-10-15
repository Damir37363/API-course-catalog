# Course Catalog API

A FastAPI backend (Lab 4) that serves the course catalog previously stored in `lib/courses.ts`: Pydantic model, list/detail routes, filtering, sorting and pagination via `Depends`.

## How to run

```bash
python -m venv .venv                 # python3 on macOS / Linux
.venv\Scripts\Activate.ps1           # Windows PowerShell
source .venv/bin/activate            # macOS / Linux

pip install -r requirements.txt
fastapi dev main.py
```

Server: http://127.0.0.1:8000 — interactive docs: http://127.0.0.1:8000/docs (also `/redoc` and `/openapi.json`).

## Routes

| Route | Description |
| --- | --- |
| `GET /` | health check |
| `GET /courses` | list; query: `is_elective`, `sort` (`popular` \| `title`), `page`, `page_size` |
| `GET /courses/{course_id}` | single course or `404 {"detail": "Course not found"}` |

## What was verified

Checked through `/docs` / an HTTP client:

| Request | Result |
| --- | --- |
| `/` | `{"message": "Course Catalog API is running"}` |
| `/courses` | 6 courses, `ai-integration` first (32 likes), `api-design` last (11) |
| `/courses/web-security` | 200, the `web-security` course |
| `/courses/nope` | 404, `{"detail": "Course not found"}` |
| `/courses?is_elective=true` | 2 courses: `ai-integration`, `api-design` |
| `/courses?is_elective=false` | 4 courses: `modern-frontend`, `web-security`, `backend-fastapi`, `databases-postgresql` |
| `/courses?sort=title` | 6 courses alphabetically: `ai-integration`, `api-design`, `backend-fastapi`, `modern-frontend`, `databases-postgresql`, `web-security` |
| `/courses?page=1&page_size=2` | `ai-integration`, `modern-frontend` |
| `/courses?page=2&page_size=2` | `web-security`, `backend-fastapi` |
| `/courses?page=3&page_size=2` | `databases-postgresql`, `api-design` |
| `/courses?page=4&page_size=2` | `[]` |
| `/docs` | exactly three routes: `GET /`, `GET /courses`, `GET /courses/{course_id}`; `Course` schema listed under Schemas |

## What changed (Lab 5)

**CORS.** `CORSMiddleware` is attached right after `app = FastAPI(...)` with `allow_origins=["http://localhost:3000"]`, `allow_methods=["*"]`, `allow_headers=["*"]`. A browser only lets a page read a response from another origin if the server answers with `access-control-allow-origin`; the Next.js frontend (`http://localhost:3000`) calls this API (`http://localhost:8000`) straight from the browser (filter, like, enrollment form), so it must be allowed. The value is an *origin* (scheme + host + port), without a path and without a trailing slash. CORS does not protect data: a request with a foreign origin is still executed (status 200), the response just has no `access-control-allow-origin`.

**camelCase in JSON.** Python keeps `snake_case`; `CamelModel` (`alias_generator=to_camel`, `validate_by_name=True`, `validate_by_alias=True`) translates the names in JSON: `is_elective` becomes `isElective`. `Course` and the enrollment models inherit from it. Query parameters are *not* renamed (`?is_elective=true`).

**New routes**

| Route | Description |
| --- | --- |
| `POST /courses/{course_id}/like` | increments `likes`, returns the updated course; `404` if there is no such course |
| `POST /enrollments` | body `{"courseId", "studentName"}` (name ≥ 2 chars); `201` + the record with an `id`; `422` for a bad body; `404` for an unknown course |
| `GET /enrollments` | list of all enrollments (to check what reached the server) |

Likes and enrollments live in the server's memory and reset on every restart (a database comes in weeks 6–7).

```text
POST /courses/web-security/like          -> 200 {"id":"web-security", ..., "isElective":false,"likes":22}
POST /courses/nope/like                  -> 404 {"detail":"Course not found"}
POST /enrollments {"courseId":"web-security","studentName":"Aigerim"}
                                         -> 201 {"courseId":"web-security","studentName":"Aigerim","id":1}
POST /enrollments {... "studentName":"A"}-> 422 detail[0].loc = ["body","studentName"],
                                            msg = "String should have at least 2 characters"
POST /enrollments {"courseId":"nope", ...} -> 404 {"detail":"Course not found"}
GET  /enrollments                        -> 200 [{"courseId":"web-security","studentName":"Aigerim","id":1}]
```

Checked with curl:

| Request | Result |
| --- | --- |
| `curl -i -H "Origin: http://localhost:3000" /` | `access-control-allow-origin: http://localhost:3000`, `vary: Origin` |
| `curl -i -H "Origin: http://evil.example" /` | 200, no `access-control-allow-origin` |
| preflight `OPTIONS /enrollments` (Origin localhost:3000, `Access-Control-Request-Method: POST`, `Access-Control-Request-Headers: content-type`) | 200, `access-control-allow-origin`, `-allow-methods` (with POST), `-allow-headers: content-type`, `access-control-max-age: 600` |
| `/courses` | six courses, camelCase keys, `ai-integration` first |
| `/courses?is_elective=true` | 2 courses (`ai-integration`, `api-design`) |
| `/courses?isElective=true` | all 6 (unknown parameter is ignored) |
| `/docs` | six routes |
