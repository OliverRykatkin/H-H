variable "environment" {
  description = "prod eller staging"
  type        = string
  validation {
    condition     = contains(["prod", "staging"], var.environment)
    error_message = "environment måste vara prod eller staging."
  }
}

variable "root_domain" {
  description = "Apex-domän"
  type        = string
  default     = "mandatorn.se"
}

variable "github_repo" {
  description = "GitHub-repo (ägare/namn) som får publicera via OIDC"
  type        = string
  default     = "OliverRykatkin/H-H"
}

variable "manage_dns" {
  description = "Skapa Route 53-zon och poster (D2). false = posterna skrivs ut som output och läggs in manuellt."
  type        = bool
  default     = true
}

variable "monthly_budget_usd" {
  description = "Månadsbudget för budgetlarmet"
  type        = number
  default     = 20
}

variable "alert_email" {
  description = "E-post för budget- och trafiklarm"
  type        = string
}

variable "cloudfront_requests_alarm_per_5min" {
  description = "Larm när en distribution får fler förfrågningar än så här per 5 minuter"
  type        = number
  default     = 500000
}

variable "draws_retention_days" {
  description = "Dragningar taggade retention=draws tas bort efter så här många dagar (D5)"
  type        = number
  default     = 7
}

variable "draws_daily_retention_days" {
  description = "En release per dygn: dragningar under draws-daily/ sparas så här länge (D5)"
  type        = number
  default     = 400
}

locals {
  prefix       = "mandatorn-${var.environment}"
  site_domain  = var.environment == "prod" ? var.root_domain : "beta.${var.root_domain}"
  data_domain  = var.environment == "prod" ? "data.${var.root_domain}" : "data.beta.${var.root_domain}"
  site_aliases = var.environment == "prod" ? [var.root_domain, "www.${var.root_domain}"] : [local.site_domain]
}
