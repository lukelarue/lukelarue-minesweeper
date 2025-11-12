variable "project_id" {
  description = "Google Cloud project ID"
  type        = string
  default     = "parabolic-env-456611-q9"
}

variable "artifact_registry_location" {
  description = "Region for Artifact Registry repositories"
  type        = string
  default     = "us-central1"
}

variable "cloud_run_location" {
  description = "Region for Cloud Run service"
  type        = string
  default     = "us-central1"
}

variable "github_repository" {
  description = "GitHub repository (owner/repo) for WIF"
  type        = string
  default     = "lukelarue/lukelarue-minesweeper"
}

variable "image_tag" {
  description = "Initial container image tag for Terraform-managed spec"
  type        = string
  default     = "latest"
}
