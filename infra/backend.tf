terraform {
  backend "gcs" {
    bucket = "lukelarue-terraform-state"
    prefix = "state/minesweeper"
  }
}
