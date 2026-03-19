# StudyGuru Backend Service

The StudyGuru backend is the primary FastAPI application for the platform. It owns authentication, subject and concept management, AI-assisted study material generation, student learning flows, quiz delivery, learning-bot interactions, and integration with the concept-visual microservice.

## What This Service Does

- Exposes REST APIs for admins and students
- Authenticates users and manages session cookies
- Generates and publishes study materials
- Coordinates LLM-backed content generation workflows
- Serves learning content, flashcards, concept resources, and quiz sessions
- Integrates with PostgreSQL for persistence
- Integrates with Google Cloud Storage when artifact storage is configured for GCS
- Calls the concept-visual microservice to generate concept images
- Exposes readiness and liveness endpoints for Cloud Run

## API Surface

Base routes:

- `GET /health/` - readiness check
- `GET /health/live` - liveness check
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/session`
- `POST /v1/study-material/...` - admin and student study material workflows
- `POST /v1/quizzes/student/sessions`
- `POST /v1/quizzes/student/assessments`

The study-material route group includes subject management, concept planning, publishing flows, concept image generation and review, learning-bot access, flashcards, resource review, and student progression endpoints.

## Core Capabilities

- Multi-tenant auth with organization-aware access control
- AI-assisted study material generation with retry and fallback behavior
- Quiz generation, submission, reporting, and topic assessment
- Learning-bot retrieval over internal content plus external evidence
- Admin review flows for concept images and learning resources
- Health checks, structured logging, and migration-based schema management

## Project Layout

```text
src/
  api/rest/                 FastAPI routers and dependencies
  config/                   Environment-backed settings
  control/                  AI orchestration, retrieval, renderers, graph workflow
  core/services/            Application services and integrations
  data/                     Postgres client, models, repositories, migrations
  schemas/                  Request and response contracts
  tools/                    Operational scripts
tests/                      Test and helper scripts
Temp/                       Experimental or draft material-generation work
```

## Local Development

### Option 1: Run with Docker Compose

From the repository root:

```bash
docker compose up --build
```

This starts:

- PostgreSQL on `localhost:5432`
- Backend on `localhost:8000`
- Concept visual service on `localhost:8002`
- Frontend on `localhost:5173`

### Option 2: Run the backend directly

```bash
cd Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## Required Configuration

The backend reads configuration from environment variables or `.env`.

Minimum production variables:

| Variable | Purpose |
| --- | --- |
| `JWT_SECRET` | Signing secret for access tokens |
| `POSTGRES_URL` or `POSTGRES_*` | Database connectivity |
| `GROQ_API` or `GROQ_API_KEY` | LLM provider credential |
| `CONCEPT_VISUAL_SERVICE_URL` | URL of the concept-visual microservice |
| `CONCEPT_VISUAL_SERVICE_TOKEN` | Shared service-to-service token |
| `CORS_ALLOW_ORIGINS` | Allowed frontend origins |
| `AUTH_COOKIE_SECURE` | Should remain `true` in production |

Commonly tuned variables:

| Variable | Purpose |
| --- | --- |
| `ARTIFACT_STORAGE_BACKEND` | `local` or `gcs` |
| `GCS_BUCKET_NAME` | Artifact bucket name when GCS is enabled |
| `MATERIAL_OUTPUT_DIR` | Local artifact output directory |
| `CONCEPT_VISUAL_OUTPUT_DIR` | Local cache path for concept-visual assets |
| `LLM_CACHE_TTL_SECONDS` | In-memory cache duration for repeated prompt calls |
| `RESOURCE_CACHE_TTL_SECONDS` | In-memory cache duration for repeated resource lookups |
| `LOG_LEVEL` | Application log level |

## Database Migrations

Schema changes are managed through versioned SQL migrations in `src/data/migrations/versions`.

Rules:

- Name files as `<version>_<snake_case_name>.sql`
- Keep migrations append-only
- Do not edit applied migrations
- The runner records file identity, version, name, and checksum in `schema_migrations`

Run migrations manually:

```bash
cd Backend
python3 -m src.data.migrations
```

Pending migrations also run automatically during application startup.

## Health and Observability

Readiness and liveness endpoints:

- `GET /health/`
- `GET /health/live`

Readiness currently validates:

- PostgreSQL connectivity
- Groq LLM reachability

The service emits structured JSON logs suitable for Cloud Run log ingestion.

## Production Deployment Notes

Recommended production topology:

- Deploy the backend as its own Cloud Run service
- Deploy the concept-visual backend as a separate internal Cloud Run service
- Use Cloud SQL for PostgreSQL
- Use GCS for durable artifact storage
- Inject all secrets through Secret Manager or CI/CD-managed environment variables

Important note:

- The concept-image flow currently works cleanly in local Docker Compose because services share the `studyguru_output` volume.
- If you deploy both services independently on Cloud Run, do not rely on local filesystem sharing between services. Use durable shared storage for generated visual assets.

## Verification

Useful local checks:

```bash
python3 -m compileall src
python3 -m pytest tests -q
```

If `pytest` is not installed in your environment, install it before running the suite.
