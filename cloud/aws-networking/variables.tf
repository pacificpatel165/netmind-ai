variable "aws_region" {
  description = "AWS region to simulate against LocalStack"
  type        = string
  default     = "us-east-1"
}

variable "project_tag" {
  description = "Tag applied to every resource, matches the project name used elsewhere in this repo"
  type        = string
  default     = "netmind-ai-aws-gap-closing"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.60.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet"
  type        = string
  default     = "10.60.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private subnet"
  type        = string
  default     = "10.60.2.0/24"
}

variable "availability_zone" {
  description = "AZ both subnets live in -- kept single-AZ deliberately, this exercise is about VPC/subnet/routing/SG concepts, not multi-AZ HA design"
  type        = string
  default     = "us-east-1a"
}

variable "admin_cidr" {
  description = "CIDR allowed to reach web-sg on port 22 -- default is open to any address since this runs against a local simulated API, not a real account; narrow this if it's ever pointed at a real AWS account"
  type        = string
  default     = "0.0.0.0/0"
}
