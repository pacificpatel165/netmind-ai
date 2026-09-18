terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Points every AWS API call at LocalStack (localhost:4566) instead of real
# AWS. Dummy credentials -- LocalStack Community Edition doesn't validate
# them, but the provider requires something non-empty to be set.
provider "aws" {
  region                      = var.aws_region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    ec2 = "http://localhost:4566"
  }
}

# --- VPC ---------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name    = "${var.project_tag}-vpc"
    Project = var.project_tag
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name    = "${var.project_tag}-igw"
    Project = var.project_tag
  }
}

# --- Subnets -------------------------------------------------------------

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block               = var.public_subnet_cidr
  availability_zone        = var.availability_zone
  map_public_ip_on_launch  = true

  tags = {
    Name    = "${var.project_tag}-public"
    Tier    = "public"
    Project = var.project_tag
  }
}

resource "aws_subnet" "private" {
  vpc_id                  = aws_vpc.main.id
  cidr_block               = var.private_subnet_cidr
  availability_zone        = var.availability_zone
  map_public_ip_on_launch  = false

  tags = {
    Name    = "${var.project_tag}-private"
    Tier    = "private"
    Project = var.project_tag
  }
}

# --- Routing ---------------------------------------------------------------
# Public route table: default route out through the IGW.
# Private route table: intentionally NO default route -- LocalStack CE
# doesn't provision real NAT Gateways, and faking outbound reachability
# with a route to nowhere would be dishonest. See README's "Known
# limitation" section.

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name    = "${var.project_tag}-public-rt"
    Project = var.project_tag
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  # No routes beyond the implicit local VPC route -- deliberate.

  tags = {
    Name    = "${var.project_tag}-private-rt"
    Project = var.project_tag
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

# --- Security groups -------------------------------------------------------
# Two-tier reference pattern: db-sg's ingress rule references web-sg's
# group ID directly, not a CIDR -- the actual point of this exercise over
# a single flat network with one permissive SG.

resource "aws_security_group" "web" {
  name        = "${var.project_tag}-web-sg"
  description = "Public-tier: HTTP/HTTPS from anywhere, SSH from admin_cidr"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH from admin"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "${var.project_tag}-web-sg"
    Project = var.project_tag
  }
}

resource "aws_security_group" "db" {
  name        = "${var.project_tag}-db-sg"
  description = "Private-tier: DB ports reachable only from web-sg, nothing else"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from web tier only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.web.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "${var.project_tag}-db-sg"
    Project = var.project_tag
  }
}
