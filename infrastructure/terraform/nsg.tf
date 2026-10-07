resource "azurerm_network_security_group" "nsg" {
  name                = "${var.prefix}-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  # Rule 1: Allow HTTPS (port 443) from anywhere
  security_rule {
    name                       = "allow-https"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # Rule 2: Allow HTTP (port 80) from anywhere
  security_rule {
    name                       = "allow-http-redirect"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # Rule 3: Allow SSH (port 22) — ACTIVE METHOD

  security_rule {
    name                   = "allow-ssh"
    priority               = 120
    direction              = "Inbound"
    access                 = "Allow"
    protocol               = "Tcp"
    source_port_range      = "*"
    destination_port_range = "22"
    source_address_prefixes = toset(concat(
      ["${chomp(data.http.my_ip.response_body)}/32"],
      var.allowed_ssh_ips
    ))
    destination_address_prefix = "*"
  }

  # Rule 4: Allow RAG UI (port 8501) from anywhere
  security_rule {
    name                       = "allow-rag-ui"
    priority                   = 130
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "8501"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # ── Rule 5: Allow RAG API (port 8058) from anywhere ──────────────────────
  # FastAPI backend for the Agentic RAG platform.
  security_rule {
    name                       = "allow-rag-api"
    priority                   = 140
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "8058"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # ── Rule 6: Deny everything else ──────────────────────────────────────────
  # Catch-all deny. Priority 4096 = lowest precedence (evaluated last).
  # Any traffic not matched by rules above is blocked here.
  security_rule {
    name                       = "deny-all-inbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}