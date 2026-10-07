# Terraform Configuration

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  required_version = ">= 1.7.0"
}

# Azure Provider

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

# Resource Group

resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location
}

# Networking 

# Virtual Network ( Vnet) for the project
resource "azurerm_virtual_network" "vnet" {
  name                = "${var.prefix}-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

# VM Subnet 
# Subnet for the VM (Nextcloud + nginx Docker containers)

resource "azurerm_subnet" "vm_subnet" {
  name                 = "${var.prefix}-vm-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Database Subnet 
# Subnet for Azure Database for PostgreSQL

resource "azurerm_subnet" "db_subnet" {
  name                 = "${var.prefix}-db-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.2.0/24"]
  # Azure PostgreSQL configures this endpoint for its own Storage access.
  service_endpoints = ["Microsoft.Storage"]

  delegation {
    name = "postgresql-delegation"

    service_delegation {
      name = "Microsoft.DBforPostgreSQL/flexibleServers"

      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
      ]
    }
  }
}

#PostgreSQL
# Private DNS zone for VNet-integrated PostgreSQL

resource "azurerm_private_dns_zone" "pg_dns" {
  name                = "${var.prefix}.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_private_dns_zone_virtual_network_link" "pg_dns_link" {
  name                  = "${var.prefix}-pg-dns-link"
  private_dns_zone_name = azurerm_private_dns_zone.pg_dns.name
  virtual_network_id    = azurerm_virtual_network.vnet.id
  resource_group_name   = azurerm_resource_group.rg.name
  registration_enabled  = false
}

#  Azure PostgreSQL Flexible Server

resource "azurerm_postgresql_flexible_server" "db" {
  name                = "${var.prefix}-pgserver-2026"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  administrator_login    = var.postgres_admin_login
  administrator_password = var.postgres_admin_password

  version = "16"

  delegated_subnet_id = azurerm_subnet.db_subnet.id
  private_dns_zone_id = azurerm_private_dns_zone.pg_dns.id

  sku_name   = "B_Standard_B1ms"
  storage_mb = 32768

  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = false

  depends_on = [
    azurerm_private_dns_zone_virtual_network_link.pg_dns_link
  ]
}

# Nextcloud Database

resource "azurerm_postgresql_flexible_server_database" "nextcloud_db" {
  name      = var.postgres_database_name
  server_id = azurerm_postgresql_flexible_server.db.id

  collation = "en_US.utf8"
  charset   = "utf8"
}


# # destroy = false means Terraform must NOT delete the existing
# storage account/container.
removed {
  from = azurerm_storage_container.nextcloud
  lifecycle {
    destroy = false
  }
}

removed {
  from = azurerm_storage_account.storage
  lifecycle {
    destroy = false
  }
}

resource "azurerm_storage_account" "blob" {
  count                    = var.enable_azure_blob_storage ? 1 : 0
  name                     = "${var.prefix}files"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
}

resource "azurerm_storage_container" "nextcloud_blob" {
  count                 = var.enable_azure_blob_storage ? 1 : 0
  name                  = "nextcloud"
  storage_account_id    = azurerm_storage_account.blob[0].id
  container_access_type = "private"
}


# Public IP
# Public IP for the Virtual Machine (VM Networking)

resource "azurerm_public_ip" "pip" {
  name                = "${var.prefix}-pip"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}


# Network Interface
# Connects the VM to the VM subnet and Public IP

resource "azurerm_network_interface" "nic" {
  name                = "${var.prefix}-nic"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.vm_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.pip.id
  }
}

# Associate the NSG with the VM network interface

resource "azurerm_network_interface_security_group_association" "nic_nsg" {
  network_interface_id      = azurerm_network_interface.nic.id
  network_security_group_id = azurerm_network_security_group.nsg.id
}

# VM bootstrap (cloud-init) 

locals {
  cloud_init = <<-CLOUDINIT
    #!/bin/bash
    set -e
    apt-get update -qq
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker ${var.admin_username}
    apt-get install -y -qq docker-compose-plugin git
    systemctl enable docker
    systemctl start docker
    ssh-keyscan github.com >> /home/${var.admin_username}/.ssh/known_hosts 2>/dev/null
    chown ${var.admin_username}:${var.admin_username} /home/${var.admin_username}/.ssh/known_hosts
  CLOUDINIT
}


# Azure Virtual Machine

resource "azurerm_linux_virtual_machine" "vm" {
  name                = "${var.prefix}-vm"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  size                = var.vm_size
  admin_username      = var.admin_username

  # cloud-init: installs Docker on first boot so CI/CD works without manual SSH
  custom_data = base64encode(local.cloud_init)

  network_interface_ids = [azurerm_network_interface.nic.id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(var.ssh_public_key_path)
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 32
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"

  }

  # custom_data is immutable — Terraform would recreate the VM if this changes.
  # Ignore it on existing VMs; cloud-init only matters when a new VM is created.

  lifecycle {
    ignore_changes = [custom_data]
  }
}
