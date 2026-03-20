provider "azurerm" {
  features {}
}

locals {
  environment_name = var.environment_name
}

# ── Resource group ─────────────────────────────────────────────────────────────

resource "azurerm_resource_group" "substrate" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    environment = var.environment_name
    managed_by  = "terraable"
  }
}

# ── Network ────────────────────────────────────────────────────────────────────

resource "azurerm_virtual_network" "substrate" {
  name                = "${var.environment_name}-vnet"
  location            = azurerm_resource_group.substrate.location
  resource_group_name = azurerm_resource_group.substrate.name
  address_space       = [var.vnet_cidr]

  tags = {
    environment = var.environment_name
    managed_by  = "terraable"
  }
}

resource "azurerm_subnet" "substrate" {
  name                 = "${var.environment_name}-subnet"
  resource_group_name  = azurerm_resource_group.substrate.name
  virtual_network_name = azurerm_virtual_network.substrate.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 8, 1)]
}

resource "azurerm_network_security_group" "substrate" {
  name                = "${var.environment_name}-nsg"
  location            = azurerm_resource_group.substrate.location
  resource_group_name = azurerm_resource_group.substrate.name

  security_rule {
    name                       = "AllowSSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = tostring(var.ssh_port)
    source_address_prefix      = var.allowed_source_prefix
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowHTTP"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = var.allowed_source_prefix
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowHTTPS"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = var.allowed_source_prefix
    destination_address_prefix = "*"
  }

  tags = {
    environment = var.environment_name
    managed_by  = "terraable"
  }
}

resource "azurerm_subnet_network_security_group_association" "substrate" {
  subnet_id                 = azurerm_subnet.substrate.id
  network_security_group_id = azurerm_network_security_group.substrate.id
}

resource "azurerm_public_ip" "substrate" {
  name                = "${var.environment_name}-pip"
  location            = azurerm_resource_group.substrate.location
  resource_group_name = azurerm_resource_group.substrate.name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    environment = var.environment_name
    managed_by  = "terraable"
  }
}

resource "azurerm_network_interface" "substrate" {
  name                = "${var.environment_name}-nic"
  location            = azurerm_resource_group.substrate.location
  resource_group_name = azurerm_resource_group.substrate.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.substrate.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.substrate.id
  }

  tags = {
    environment = var.environment_name
    managed_by  = "terraable"
  }
}

# ── Compute ────────────────────────────────────────────────────────────────────

resource "azurerm_linux_virtual_machine" "substrate" {
  name                = var.environment_name
  location            = azurerm_resource_group.substrate.location
  resource_group_name = azurerm_resource_group.substrate.name
  size                = var.vm_size
  admin_username      = var.ssh_user

  network_interface_ids = [azurerm_network_interface.substrate.id]

  admin_ssh_key {
    username   = var.ssh_user
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 64
  }

  source_image_reference {
    publisher = "RedHat"
    offer     = "RHEL"
    sku       = "9-lvm-gen2"
    version   = "latest"
  }

  disable_password_authentication = true

  tags = {
    environment = var.environment_name
    managed_by  = "terraable"
  }
}

# ── Outputs ────────────────────────────────────────────────────────────────────

output "environment_name" {
  description = "Environment identifier passed to Ansible workflows"
  value       = local.environment_name
}

output "target_platform" {
  description = "Selected target platform"
  value       = "azure"
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
    api_endpoint            = "https://${azurerm_public_ip.substrate.ip_address}"
  }
}

output "public_ip" {
  description = "Public IP address of the substrate VM"
  value       = azurerm_public_ip.substrate.ip_address
}

output "resource_group_name" {
  description = "Azure resource group containing substrate resources"
  value       = azurerm_resource_group.substrate.name
}
