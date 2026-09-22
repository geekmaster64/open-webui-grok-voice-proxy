variable "vsphere_user" {
  type = string
}

variable "vsphere_password" {
  type      = string
  sensitive = true
}

variable "vsphere_server" {
  type        = string
  description = "vCenter FQDN or IP"
}

variable "vsphere_allow_unverified_ssl" {
  type    = bool
  default = true
}

variable "datacenter" {
  type = string
}

variable "cluster" {
  type        = string
  description = "Compute cluster that holds the R740XD"
}

variable "datastore" {
  type = string
}

variable "network" {
  type        = string
  description = "Port group on the same VLAN as clients (10.20.10.0/24)"
}

variable "template" {
  type        = string
  description = "Ubuntu Server template to clone"
}

variable "vm_name" {
  type    = string
  default = "hexxus-ai-01"
}

variable "num_cpus" {
  type    = number
  default = 2
}

variable "memory_mb" {
  type    = number
  default = 8192
}

variable "disk_gb" {
  type        = number
  default     = 80
  description = "Thin-provisioned OS disk in GB"
}

variable "ipv4_address" {
  type    = string
  default = "10.20.10.150"
}

variable "ipv4_netmask" {
  type    = number
  default = 24
}

variable "ipv4_gateway" {
  type    = string
  default = "10.20.10.1"
}

variable "dns_servers" {
  type    = list(string)
  default = ["10.20.10.10", "10.20.10.11"]
}

variable "ssh_public_key" {
  type        = string
  description = "Authorized key for the btahedl login user"
}

variable "folder" {
  type    = string
  default = ""
}
