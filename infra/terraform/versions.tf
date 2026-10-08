terraform {
  required_version = ">= 1.6.0"

  backend "s3" {
    bucket         = "s3-bucket-carga-data"
    key            = "terraform/cencosud-reconciliation.tfstate"
    region         = "us-east-2"
    dynamodb_table = "cencosud-reconciliation-dev-tf-lock"
    encrypt        = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}
