locals {
  environment_name = var.environment_name
}

# ── Network ────────────────────────────────────────────────────────────────────

resource "aws_vpc" "substrate" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "${var.environment_name}-vpc"
    Environment = var.environment_name
    ManagedBy   = "terraable"
  }
}

resource "aws_internet_gateway" "substrate" {
  vpc_id = aws_vpc.substrate.id

  tags = {
    Name        = "${var.environment_name}-igw"
    Environment = var.environment_name
    ManagedBy   = "terraable"
  }
}

resource "aws_subnet" "substrate" {
  vpc_id                  = aws_vpc.substrate.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 1)
  map_public_ip_on_launch = true
  availability_zone       = data.aws_availability_zones.available.names[0]

  tags = {
    Name        = "${var.environment_name}-subnet"
    Environment = var.environment_name
    ManagedBy   = "terraable"
  }
}

resource "aws_route_table" "substrate" {
  vpc_id = aws_vpc.substrate.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.substrate.id
  }

  tags = {
    Name        = "${var.environment_name}-rt"
    Environment = var.environment_name
    ManagedBy   = "terraable"
  }
}

resource "aws_route_table_association" "substrate" {
  subnet_id      = aws_subnet.substrate.id
  route_table_id = aws_route_table.substrate.id
}

# ── Security ───────────────────────────────────────────────────────────────────

resource "aws_security_group" "substrate" {
  name        = "${var.environment_name}-sg"
  description = "Terraable substrate ingress for SSH, HTTP, and HTTPS"
  vpc_id      = aws_vpc.substrate.id

  ingress {
    description = "SSH"
    from_port   = var.ssh_port
    to_port     = var.ssh_port
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.environment_name}-sg"
    Environment = var.environment_name
    ManagedBy   = "terraable"
  }
}

# ── Compute ────────────────────────────────────────────────────────────────────

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "rhel9" {
  most_recent = true
  owners      = ["309956199498"] # Red Hat

  filter {
    name   = "name"
    values = ["RHEL-9*GA*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_key_pair" "substrate" {
  key_name   = "${var.environment_name}-key"
  public_key = var.ssh_public_key

  tags = {
    Environment = var.environment_name
    ManagedBy   = "terraable"
  }
}

resource "aws_instance" "substrate" {
  ami                    = data.aws_ami.rhel9.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.substrate.id
  vpc_security_group_ids = [aws_security_group.substrate.id]
  key_name               = aws_key_pair.substrate.key_name

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 20
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required" # Enforce IMDSv2
  }

  tags = {
    Name        = var.environment_name
    Environment = var.environment_name
    ManagedBy   = "terraable"
  }
}

# ── Outputs ────────────────────────────────────────────────────────────────────

output "environment_name" {
  description = "Environment identifier passed to Ansible workflows"
  value       = local.environment_name
}

output "target_platform" {
  description = "Selected target platform"
  value       = "aws"
}

output "portal_impl" {
  description = "Selected portal implementation"
  value       = var.portal_impl
}

output "security_profile" {
  description = "Selected security profile"
  value       = var.security_profile
}

output "connection" {
  description = "Connection details consumed by the handoff contract"
  value = {
    ansible_inventory_group = var.ansible_inventory_group
    ssh_user                = var.ssh_user
    ssh_port                = var.ssh_port
    api_endpoint            = "https://${aws_instance.substrate.public_dns}"
  }
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.substrate.id
}

output "public_ip" {
  description = "Public IP address of the substrate instance"
  value       = aws_instance.substrate.public_ip
}
