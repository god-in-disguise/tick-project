resource "digitalocean_droplet" "tick" {
  name       = var.droplet_name
  region     = var.region
  size       = var.size
  image      = "ubuntu-24-04-x64"
  monitoring = true
  ipv6       = true
  ssh_keys   = [var.ssh_key_fingerprint]
  user_data  = file("${path.module}/../scripts/bootstrap.sh")
  tags       = ["tick", "private-demo"]
}
resource "digitalocean_firewall" "tick" {
  name        = "${var.droplet_name}-firewall"
  droplet_ids = [digitalocean_droplet.tick.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "udp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

resource "digitalocean_project" "tick" {
  name        = "TICK"
  description = "TICK private demo"
  purpose     = "Web Application"
  environment = "Development"
  resources   = [digitalocean_droplet.tick.urn]
}
