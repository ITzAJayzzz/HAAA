variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-southeast-1" # Singapore — close to Philippines
}

variable "app_name" {
  description = "Application name prefix for all resources"
  type        = string
  default     = "globaltalk"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "ssh_public_key_path" {
  description = "Path to your SSH public key file"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "ssh_allowed_cidr" {
  description = "CIDR block allowed to SSH. Restrict to your IP in production."
  type        = string
  default     = "0.0.0.0/0"
}
