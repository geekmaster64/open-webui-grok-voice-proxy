# vSphere VM only. Docker/nginx/proxy stay in Ansible (or bootstrap.sh).
# Do not wrap `docker run` here.

data "vsphere_datacenter" "dc" {
  name = var.datacenter
}

data "vsphere_compute_cluster" "cluster" {
  name          = var.cluster
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_datastore" "ds" {
  name          = var.datastore
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_network" "net" {
  name          = var.network
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_virtual_machine" "template" {
  name          = var.template
  datacenter_id = data.vsphere_datacenter.dc.id
}

locals {
  cloudinit = templatefile("${path.module}/cloud-init.yaml", {
    ssh_public_key = var.ssh_public_key
  })
}

resource "vsphere_virtual_machine" "gateway" {
  name             = var.vm_name
  resource_pool_id = data.vsphere_compute_cluster.cluster.resource_pool_id
  datastore_id     = data.vsphere_datastore.ds.id
  folder           = var.folder != "" ? var.folder : null
  firmware         = "efi"
  guest_id         = data.vsphere_virtual_machine.template.guest_id
  scsi_type        = data.vsphere_virtual_machine.template.scsi_type
  num_cpus         = var.num_cpus
  memory           = var.memory_mb
  sync_time_with_host = true

  network_interface {
    network_id   = data.vsphere_network.net.id
    adapter_type = "vmxnet3"
  }

  disk {
    label            = "disk0"
    size             = max(var.disk_gb, data.vsphere_virtual_machine.template.disks.0.size)
    thin_provisioned = true
    eagerly_scrub    = false
  }

  clone {
    template_uuid = data.vsphere_virtual_machine.template.id

    customize {
      linux_options {
        host_name = var.vm_name
        domain    = "hexxus.net"
      }

      network_interface {
        ipv4_address = var.ipv4_address
        ipv4_netmask = var.ipv4_netmask
      }

      ipv4_gateway    = var.ipv4_gateway
      dns_server_list = var.dns_servers
      dns_suffix_list = ["hexxus.net"]
    }
  }

  extra_config = {
    "guestinfo.userdata"          = base64encode(local.cloudinit)
    "guestinfo.userdata.encoding" = "base64"
  }

  lifecycle {
    ignore_changes = [extra_config]
  }
}

output "name" {
  value = vsphere_virtual_machine.gateway.name
}

output "ipv4" {
  value = var.ipv4_address
}
