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
