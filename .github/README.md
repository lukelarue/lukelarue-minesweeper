# Minesweeper CI/CD Strategy

## Overview

This repository uses GitHub Actions and Terraform together to build, test, and deploy the Minesweeper service to Cloud Run. Terraform owns the **infrastructure shape** (Artifact Registry, Cloud Run service, service accounts, Workload Identity Federation), while GitHub Actions owns the **container image rollout** by deploying a pinned digest to Cloud Run.

Terraform's Cloud Run resource is configured with `lifecycle.ignore_changes` on the container image field so that new image digests deployed by CI **do not** show up as drift in `terraform plan`.

## Workflows

### `.github/workflows/tests.yml`

- **Trigger**
  - `on: push`
  - `on: workflow_dispatch`
- **Purpose**
  - Fast feedback on lint and unit tests for all branches.
- **Steps**
  - Checkout repo.
  - Set up Python 3.11.
  - Install `requirements.txt` plus `ruff`.
  - Run `ruff check .`.
  - Run `pytest -q`.

### `.github/workflows/image-publish.yml`

- **Trigger**
  - Pushes to `main` that touch:
    - `app/**`, `minesweeper/**`, `frontend/**`
    - `Dockerfile`, `requirements.txt`
    - The workflow file itself.
  - Manual `workflow_dispatch`.
- **Jobs**
  - **`test` job**
    - Same Python lint + pytest steps as `tests.yml`.
    - Builds a Docker image using the repo `Dockerfile`.
    - Uses Node + `firebase-tools` to run the Python tests inside the image, under a Firestore emulator (`emulators:exec --only firestore ...`).
  - **`build-and-deploy` job**
    - Depends on `test`.
    - Verifies required GitHub repository variables are set:
      - `GCP_PROJECT_ID`
      - `GCP_WORKLOAD_IDENTITY_PROVIDER`
      - `GCP_DEPLOY_SA_EMAIL`
      - `ARTIFACT_REGISTRY_HOST`
      - `CLOUD_RUN_REGION`
    - Authenticates to Google Cloud via Workload Identity Federation using `google-github-actions/auth@v2`.
    - Logs into Artifact Registry with `docker/login-action@v3`.
    - Builds and pushes the image with `docker/build-push-action@v5` to:
      - `${ARTIFACT_REGISTRY_HOST}/${GCP_PROJECT_ID}/minesweeper/minesweeper:${GITHUB_SHA}`
      - `${ARTIFACT_REGISTRY_HOST}/${GCP_PROJECT_ID}/minesweeper/minesweeper:latest`
    - Deploys to Cloud Run using `google-github-actions/deploy-cloudrun@v2`:
      - Service name: `minesweeper`
      - Region: `${CLOUD_RUN_REGION}`
      - Image: pushed Artifact Registry image pinned by digest.
    - Writes a short deployment summary (image name and digest) to `$GITHUB_STEP_SUMMARY`.

## Required GitHub repository variables

Set these in **Repository Settings → Variables** for `lukelarue/lukelarue-minesweeper`:

- `GCP_PROJECT_ID` – target GCP project ID.
- `GCP_WORKLOAD_IDENTITY_PROVIDER` – value from Terraform output `workload_identity_provider_name` in `infra/`.
- `GCP_DEPLOY_SA_EMAIL` – value from Terraform output `minesweeper_deploy_sa_email` in `infra/`.
- `ARTIFACT_REGISTRY_HOST` – e.g. `us-central1-docker.pkg.dev`.
- `CLOUD_RUN_REGION` – e.g. `us-central1`.

## Terraform vs CI ownership

- **Terraform (`infra/`)** provisions:
  - Artifact Registry repo `minesweeper`.
  - Cloud Run service `minesweeper` (port 8080).
  - Runtime and deploy service accounts and IAM roles.
  - Workload Identity Federation provider bound to this GitHub repo.
- **GitHub Actions**:
  - Builds and pushes new container images.
  - Deploys new Cloud Run revisions using pinned digests.

Because the Cloud Run image field is ignored by Terraform (`lifecycle.ignore_changes`), you can safely:

- Rerun Terraform to change infra without affecting the currently deployed image.
- Push to `main` to roll out a new image via CI/CD without causing Terraform drift.
