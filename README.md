# Minesweeper (FastAPI + Firestore)

Python 3.11+ FastAPI service implementing a Minesweeper game with a minimal iframe-friendly frontend and Firestore persistence.

## Features

- Game engine in pure Python (`minesweeper/game_engine.py`)
- Persistence layer with Firestore and in-memory implementation
- REST API (`/api/minesweeper`) with endpoints: start, state, reveal, flag, abandon
- Minimal frontend (no framework) you can embed via `<iframe>`
- Tests for engine and API using pytest

## Quickstart (Local, without emulator)

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
set USE_INMEMORY=1  # PowerShell: $env:USE_INMEMORY=1
uvicorn app.main:app --reload
# Open http://localhost:8000
```

## Local Dev with Firestore Emulator

### Option A: Using Docker Compose (cross-platform)

```bash
docker compose up --build
# Backend at http://localhost:8000, emulator at http://localhost:8080
```

If the emulator image fails due to missing components, run Option B.

### Option B: Run Emulator with gcloud locally

1) Install the Google Cloud SDK and components.

2) Start the emulator:

```bash
gcloud beta emulators firestore start --host-port=localhost:8080
```

3) In another terminal, run the app pointing at the emulator:

```bash
$env:FIRESTORE_EMULATOR_HOST="localhost:8080"  # Windows PowerShell
$env:GOOGLE_CLOUD_PROJECT="fake-minesweeper-local"
uvicorn app.main:app --reload
```

Open http://localhost:8000

## API

Base path: `/api/minesweeper`

- POST `/start` body: `{ "board_width": 10, "board_height": 10, "num_mines": 15 }`
- GET `/state`
- POST `/reveal` body: `{ "row": 3, "col": 5 }`
- POST `/flag` body: `{ "row": 3, "col": 5 }`
- POST `/abandon`

Auth stub: supply `X-User-Id` header. If omitted and `ALLOW_ANON=1`, defaults to `DEFAULT_USER_ID`.

## Testing

```bash
pytest -q
```

API tests use the in-memory persistence by constructing the app with `create_app(persistence=InMemoryPersistence())`.

## Deploy (Cloud Run)

- Build container using the provided Dockerfile.
- Ensure `GOOGLE_CLOUD_PROJECT` is set and credentials are available to the service account.
- Do not set `FIRESTORE_EMULATOR_HOST` in production.

## Project Structure

- `minesweeper/` game engine and persistence
- `app/` FastAPI app
- `frontend/` static assets (served at `/`)
- `tests/` pytest suite
