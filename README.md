# Minesweeper (FastAPI + Firestore)

Python 3.11+ FastAPI service implementing a Minesweeper game with a minimal iframe-friendly frontend and Firestore persistence.

## Features

- Game engine in pure Python (`minesweeper/game_engine.py`)
- Persistence layer with Firestore and in-memory implementation
- REST API (`/api/minesweeper`) with endpoints: start, state, reveal, flag, abandon
- Minimal frontend (no framework) you can embed via `<iframe>`
- Tests for engine and API using pytest

## Quickstart (Local, Firestore emulator)

```bash
python -m venv .venv
# Windows PowerShell
. .venv/Scripts/Activate.ps1
# Windows Cmd
.venv\Scripts\activate.bat
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.local.example` to `.env.local`, or create it with:

```makefile
USE_INMEMORY=0
FIRESTORE_EMULATOR_HOST=localhost:8080
GOOGLE_CLOUD_PROJECT=fake-minesweeper-local
ALLOW_ANON=1
DEFAULT_USER_ID=local-demo
```

Start the Firestore emulator (choose one):

```bash
# Option A: Docker Compose (starts only the emulator)
docker compose up -d emulator

# Option B: gcloud (run in a separate terminal)
gcloud beta emulators firestore start --host-port=localhost:8080
```

Run the server in another terminal:

```bash
uvicorn app.main:app --reload
# Open http://localhost:8000
```

On startup you will see a log line indicating which persistence is active, for example:

```bash
[minesweeper] Persistence=FirestorePersistence USE_INMEMORY=0 FIRESTORE_EMULATOR_HOST=localhost:8080 GOOGLE_CLOUD_PROJECT=fake-minesweeper-local
```

### About `.env.local` files

`.env.local` files are used to store environment variables for local development. They are not committed to the repository and are ignored by Git. This allows you to keep your local environment settings separate from the production environment.

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

### Infra (Terraform)

This repo includes a Terraform package under `infra/` to provision:

- Artifact Registry repository `minesweeper`
- Cloud Run service `minesweeper` (port 8080)
- Runtime and Deploy service accounts and roles
- Workload Identity Federation provider for this repo

Apply:

```bash
terraform -chdir=infra init
terraform -chdir=infra apply
```

Terraform outputs include the Cloud Run URL. Use that for embedding.

### GitHub Variables (this repo)

Set the following in the repository settings → Variables:

- `GCP_PROJECT_ID` = your GCP project id
- `GCP_WORKLOAD_IDENTITY_PROVIDER` = value from `infra` output `workload_identity_provider_name`
- `GCP_DEPLOY_SA_EMAIL` = value from `infra` output `minesweeper_deploy_sa_email`
- `GCP_ARTIFACT_REGISTRY_HOST` = `us-central1-docker.pkg.dev`
- `CLOUD_RUN_REGION` = `us-central1`

### CI/CD

On pushes to `main`, `.github/workflows/image-publish.yml`:

- Authenticates via WIF
- Builds and pushes `minesweeper` image to Artifact Registry
- Deploys a new Cloud Run revision for `minesweeper`

`.github/workflows/tests.yml` runs lint (ruff) and pytest.

### Embedding in lukelaruecom website

- In the website repo, set `VITE_MINESWEEPER_URL` (repository variable) to the Cloud Run URL output by Terraform.
- The website build picks it up and the lobby iframe will point to that URL.

## Project Structure

- `minesweeper/` game engine and persistence
- `app/` FastAPI app
- `frontend/` static assets (served at `/`)
- `tests/` pytest suite
