variable "droplet_name" {
  type    = string
  default = "tick-demo"
}
variable "region" {
  type    = string
  default = "fra1"
}

variable "size" {
  type    = string
  default = "s-2vcpu-4gb"
}

variable "ssh_key_fingerprint" {
  type      = string
  sensitive = true
}
