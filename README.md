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
