output "droplet_ip" {
  value = digitalocean_droplet.tick.ipv4_address
}

output "droplet_id" {
  value = digitalocean_droplet.tick.id
}

output "api_hostname" {
  value = "${digitalocean_droplet.tick.ipv4_address}.sslip.io"
}
