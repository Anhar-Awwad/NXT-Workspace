output "vm_public_ip" {
  description = "Public IP address of the Nextcloud VM"
  value       = azurerm_public_ip.pip.ip_address
}

output "ssh_command" {
  description = "SSH command to connect to the VM"
  value       = "ssh ${var.admin_username}@${azurerm_public_ip.pip.ip_address}"
}

output "nextcloud_url" {
  description = "Nextcloud URL after deployment"
  value       = "https://${azurerm_public_ip.pip.ip_address}"
}

# ─── Database ─────────────────────────────────────────────────────────────────

output "postgres_fqdn" {
  description = "PostgreSQL server FQDN — paste this as POSTGRES_HOST in your .env"
  value       = azurerm_postgresql_flexible_server.db.fqdn
}

# ─── Storage (only present when enable_azure_blob_storage = true) ────────────

output "storage_account_name" {
  description = "Azure Storage Account name — paste as OBJECTSTORE_AZURE_ACCOUNT in your .env"
  value       = var.enable_azure_blob_storage ? azurerm_storage_account.blob[0].name : null
}

output "storage_account_key" {
  description = "Azure Storage Account primary key — paste as OBJECTSTORE_AZURE_KEY in your .env"
  value       = var.enable_azure_blob_storage ? azurerm_storage_account.blob[0].primary_access_key : null
  sensitive   = true
}

output "storage_container_name" {
  description = "Azure Blob container name — paste as OBJECTSTORE_AZURE_CONTAINER in your .env"
  value       = var.enable_azure_blob_storage ? azurerm_storage_container.nextcloud_blob[0].name : null
}