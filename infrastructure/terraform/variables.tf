variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the Azure resource group"
  type        = string
}

variable "location" {
  description = "Azure region for the resources"
  type        = string
}

variable "prefix" {
  description = "Prefix used for naming Azure resources"
  type        = string
}

variable "vm_size" {
  description = "Azure VM size — runs Nextcloud + nginx + the RAG stack (rag-api/rag-ui/rag-db) together"
  type        = string
}

variable "admin_username" {
  description = "Admin username for the Azure VM"
  type        = string
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key"
  type        = string
}

variable "allowed_ssh_ips" {
  description = "Public IP addresses allowed to connect through SSH"
  type        = list(string)
  default     = []
}

variable "postgres_admin_login" {
  description = "Administrator username for PostgreSQL"
  type        = string
}

#Azure Database for PostgreSQL Flexible Server 
variable "postgres_admin_password" {
  description = "Administrator password for PostgreSQL"
  type        = string
  sensitive   = true
}
variable "postgres_database_name" {
  description = "Name of the PostgreSQL database"
  type        = string
}

# Azure Blob Storage (optional) 

variable "enable_azure_blob_storage" {
  description = "Provision Azure Blob Storage as Nextcloud's primary file store (production only). Default false keeps files on the VM disk -- correct for local dev, VPS, and any non-Azure deployment."
  type        = bool
  default     = false
}