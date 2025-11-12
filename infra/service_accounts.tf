locals {
  runtime_roles = [
    "roles/datastore.user",
    "roles/logging.logWriter"
  ]

  deploy_roles = [
    "roles/run.admin",
    "roles/artifactregistry.writer"
  ]
}

resource "google_service_account" "minesweeper_runtime" {
  account_id   = "minesweeper-runtime"
  display_name = "Minesweeper Cloud Run runtime"
}

resource "google_service_account" "minesweeper_deploy" {
  account_id   = "minesweeper-deploy"
  display_name = "Minesweeper CI/CD deploy automation"
}

resource "google_project_iam_member" "runtime_roles" {
  for_each = toset(local.runtime_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.minesweeper_runtime.email}"
}

resource "google_project_iam_member" "deploy_roles" {
  for_each = toset(local.deploy_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.minesweeper_deploy.email}"
}

resource "google_service_account_iam_member" "deploy_can_use_runtime" {
  service_account_id = google_service_account.minesweeper_runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.minesweeper_deploy.email}"
}

output "minesweeper_runtime_sa_email" {
  value = google_service_account.minesweeper_runtime.email
}

output "minesweeper_deploy_sa_email" {
  value = google_service_account.minesweeper_deploy.email
}
