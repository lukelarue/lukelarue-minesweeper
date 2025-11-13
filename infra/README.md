# Minesweeper Infra (Terraform)

This package provisions the Google Cloud resources needed to build and run Minesweeper:

- Artifact Registry repository `minesweeper`
- Cloud Run service `minesweeper` (port 8000)
- Runtime and Deploy service accounts with least-privileged roles
- Workload Identity Federation provider for this repo (`lukelarue/lukelarue-minesweeper`)

## Prerequisites

- GCP project with billing enabled and Firestore already initialized (Native mode)
- Authenticated with gcloud and Application Default Credentials:
  - `gcloud auth application-default login`
- Terraform state bucket `lukelarue-terraform-state` exists

## Variables

- `project_id` (default: `parabolic-env-456611-q9`)
- `artifact_registry_location` (default: `us-central1`)
- `cloud_run_location` (default: `us-central1`)
- `github_repository` (default: `lukelarue/lukelarue-minesweeper`)
- `image_tag` (default: `latest`)

## Apply

```
terraform -chdir=infra init
terraform -chdir=infra apply
```

Outputs include:

- `minesweeper_service_url` – Cloud Run URL to embed in the website iframe
- `workload_identity_provider_name` – Use as `GCP_WORKLOAD_IDENTITY_PROVIDER` in this repo's GitHub Variables
- `minesweeper_deploy_sa_email` – Use as `GCP_DEPLOY_SA_EMAIL` in this repo's GitHub Variables

## GitHub Variables (this repo)

Set these in GitHub Repository Variables for `lukelarue/lukelarue-minesweeper`:

- `GCP_PROJECT_ID` = your GCP project id (e.g. `parabolic-env-456611-q9`)
- `GCP_WORKLOAD_IDENTITY_PROVIDER` = value from `workload_identity_provider_name` output
- `GCP_DEPLOY_SA_EMAIL` = value from `minesweeper_deploy_sa_email` output
- `GCP_ARTIFACT_REGISTRY_HOST` = `us-central1-docker.pkg.dev`
- `CLOUD_RUN_REGION` = `us-central1`

## Website embedding

Prefer embedding the Cloud Run URL (cross-origin) in the website lobby. Set `VITE_MINESWEEPER_URL` in the website repo variables to the value of `minesweeper_service_url`.

## Firestore data model and how it is used

The Minesweeper service persists game state in Firestore (Native mode). The schema is intentionally simple and keyed by a stable user identifier so that each player only ever reads or mutates their own game.

- `minesweeperGames` (collection)
  - One document per user. The document ID is the resolved user ID (typically their email when behind Google/IAP, or a dev-provided header/local ID).
  - Fields include:
    - `board_width`, `board_height`, `num_mines`
    - `status` (active, won, lost, abandoned, error)
    - `mine_layout`, `revealed_mask`, `flag_mask`
    - `moves_count`, `mines_placed`, `rng_seed`
    - Timestamps: `created_at`, `updated_at`, `finished_at`, `first_reveal_at`
    - Results: `result_time_ms`, `end_result`, `final_score` (reserved)
  - The server reads/writes this document inside transactions to ensure consistency.

- `minesweeperGames/{userId}/moves` (subcollection)
  - Append-only move history for that user’s current/last game.
  - Document ID is a zero-padded sequence like `000001`, `000002`, ...
  - Fields include `seq`, `action` (reveal|flag|abandon|error), `row`, `col`, `timestamp`, `hit_mine`, `cleared_cells`, `flags_total`, `revealed_total`, `status_after`, `ms_since_game_start`, `ms_since_prev_move`, and optional `error_reason`.

### Per-user isolation (how we resolve user identity)

The backend determines the user ID from request headers and uses it as the Firestore document ID. In production (Cloud Run), it prefers trusted Google headers and disables anonymous fallbacks by default:

Order of precedence:
1. `X-Goog-Authenticated-User-Email` or `X-Authenticated-User-Email` or `X-Forwarded-Email` (e.g. `accounts.google.com:alice@example.com` → `alice@example.com`)
2. `X-Forwarded-User`
3. `X-User-Id` only if `TRUST_X_USER_ID=1` (intended for dev/tests)
4. Anonymous fallback only if `ALLOW_ANON=1` (dev convenience)

Environment flags influencing behavior:
- `TRUST_X_USER_ID`: default off in Cloud Run, on in local dev.
- `ALLOW_ANON`: default off in Cloud Run, on in local dev.
- `DEFAULT_USER_ID`: default `local-user` when anonymous fallback is enabled.
- `FIRESTORE_EMULATOR_HOST`: if set, the server connects to the emulator; otherwise it connects to the project.
- `GOOGLE_CLOUD_PROJECT`: Firestore project to use.

Because each request is resolved to a specific user ID, reads and writes hit `minesweeperGames/{userId}` only. This guarantees that two different users never see or affect each other’s boards.
