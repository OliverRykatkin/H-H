terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
  # State i S3 konfigureras vid init (se infra/README.md):
  #   terraform init -backend-config="bucket=<state-bucket>" -backend-config="key=mandatorn/<env>.tfstate"
  backend "s3" {
    region       = "eu-north-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = "eu-north-1"
  default_tags {
    tags = {
      project     = "mandatorn"
      environment = var.environment
      managed_by  = "terraform"
    }
  }
}

# CloudFront-certifikat och CloudFront-mätvärden finns bara i us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = {
      project     = "mandatorn"
      environment = var.environment
      managed_by  = "terraform"
    }
  }
}
