output "droplet_ip" {
  value = digitalocean_droplet.tick.ipv4_address
}
output "api_hostname" {
  value = "${digitalocean_droplet.tick.ipv4_address}.sslip.io"
}
