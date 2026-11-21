# OpenStack Lab: Post-Deployment Configuration, Resource Provisioning & Live Migration Guide
**Platform:** 4-Node OpenStack Cluster (1 Controller + 3 Compute Hypervisors)  
**Deployment Context:** Post-Kolla deployment phase (Networking, Storage, Observability, Telemetry & Live Migration)  
**Repository Target:** `https://github.com/Yashshah025/files`

---

## 1. Cloud Resources Setup (`openstack/01-cloud-setup.sh`)

Once OpenStack core services are deployed, the environment requires baseline software-defined networking, image catalogs, VM flavors, and firewall rules to host tenant workloads.

### What Was Provisioned:

1. **External Provider Network (`provider-net`)**
   * **Network Type:** Flat network mapped to physical network interface `physnet1` (VLAN 60).
   * **Subnet:** `172.24.4.0/24`, with gateway `172.24.4.1` on `br-ex`.
   * **Floating IP Pool:** `172.24.4.100` – `172.24.4.199`.
   * **Role:** Enables routable public IP assignment so instances can communicate externally and accept inbound SSH/HTTP traffic.

2. **Tenant Virtual Network & Virtual Router (`private-net` + `r1`)**
   * **Subnet:** `192.168.50.0/24` with automated DHCP managed by Neutron.
   * **Router `r1`:** Connects `private-net` to `provider-net` as its default external gateway.
   * **Role:** Provides isolated virtual tenant networking with outbound SNAT to the internet.

3. **Base OS Cloud Image (`cirros`)**
   * **Image:** CirrOS 0.6.2 (x86_64), uploaded into Glance as a public image.
   * **Role:** Lightweight kernel-testing image (~16 MB) used for rapid instance provisioning and live-migration testing.

4. **Compute Sizing Flavors**
   * Defined standardized instance tiers matching CloudKitty billing rules:
     * `m1.tiny`: 1 vCPU, 512 MB RAM, 5 GB Disk
     * `m1.small`: 1 vCPU, 1024 MB RAM, 10 GB Disk
     * `m1.medium`: 2 vCPUs, 2048 MB RAM, 20 GB Disk
     * `m1.large`: 4 vCPUs, 4096 MB RAM, 40 GB Disk

5. **Security Rules & Access Keypair**
   * Default security group updated with ICMP (ping) and TCP port 22 (SSH) ingress rules.
   * Generated Ed25519/RSA SSH keypair `mykey.pem` for passwordless instance login.

### Execution Command:
```bash
cd ~/Cloud-Project
openstack/01-cloud-setup.sh
```

---

## 2. Infrastructure Exporter & Observability (`ansible/05-exporter.yml`)

To export OpenStack operational metrics into Prometheus, an independent exporter service is installed on the control plane.

### What Was Provisioned:
* Created an isolated virtual environment at `/opt/cloud-exporter/venv`.
* Installed `openstacksdk` to authenticate and interact with Keystone, Nova, and Neutron APIs.
* Deployed and started the `cloud-exporter.service` systemd daemon listening on management IP `10.0.10.11:9199`.
* Verified metric exposition at `http://10.0.10.11:9199/metrics`.

### Execution Command:
```bash
cd ~/Cloud-Project/ansible
ansible-playbook 05-exporter.yml
```

---

## 3. Telemetry & Rating Engine Configuration (`openstack/02-billing-rates.sh`)

CloudKitty serves as the pricing and rating engine for resource consumption metrics gathered by Ceilometer and Gnocchi.

### What Was Configured:
* Enabled the `hashmap` rating module with priority `100`.
* Assigned hourly flat pricing to compute flavors:
  * `m1.tiny`: 0.01 credits/hour
  * `m1.small`: 0.02 credits/hour
  * `m1.medium`: 0.04 credits/hour
  * `m1.large`: 0.08 credits/hour
* Configured auxiliary rating rules:
  * Volume storage: `0.0002` credits per GiB-hour
  * Floating IPs: `0.005` credits per IP-hour
  * Outbound bandwidth: `0.00001` credits per MB
  * Glance image storage: `0.000002` credits per MiB-hour

### Execution Command:
```bash
cd ~/Cloud-Project
openstack/02-billing-rates.sh
```

---

## 4. End-to-End Zero-Downtime Live Migration (`live-migration/test.sh`)

Live migration validates that shared GlusterFS storage (`/var/lib/nova-shared`) and VLAN 10 management connectivity operate synchronously without data corruption or network dropped states.

### Execution Process & Architectural Mechanics:
1. Booted an active test instance (`lm-test`) pinned specifically to `cloud03-compute01`.
2. Initiated live migration to `cloud03-compute02` using `block_migration=False`:
   * **Storage Handling:** Because instance disk images reside on `/var/lib/nova-shared`, no virtual disk data is copied across the network.
   * **Memory State Transfer:** QEMU/KVM transfers dirty RAM pages and CPU register states over the management VLAN (`10.0.10.x`).
3. Migrated the instance back from `cloud03-compute02` to `cloud03-compute01`.
4. Verified continuous uptime, successful memory convergence, and completed cleanup.

### Execution Command:
```bash
cd ~/Cloud-Project
live-migration/test.sh cloud03-compute01 cloud03-compute02
openstack server delete lm-test
```

---

## 5. Grafana Dashboard Generation & Integration

To visualize telemetry, system health, and migration analytics, customized Grafana dashboards were compiled and installed into Kolla's provisioning structure.

### Deployed Dashboards:
1. **`Cloud03 / Cluster overview`:** Aggregate cluster vCPU, RAM, disk, and instance statistics.
2. **`Cloud03 / Compute and VMs`:** Per-hypervisor performance graphs for all compute hosts.
3. **`Cloud03 / Platform health`:** Hardware utilization, thermal metrics, and network interface carrier stats.
4. **`Cloud03 / Live migration and balance`:** Historical and active VM migrations, hypervisor distribution.
5. **`Cloud03 / OpenStack resources`:** API availability, endpoint response metrics, and worker status.
6. **`Cloud03 / Billing (CloudKitty)`:** Rating breakdown and accumulated tenant credit consumption.
7. **`Cloud03 / Projects and usage`:** Tenant quota allocation and distribution across projects.

### Execution Commands:
```bash
cd ~/Cloud-Project/monitoring
python3 make_dashboards.py

sudo mkdir -p /etc/kolla/config/grafana/dashboards
sudo cp -a ~/Cloud-Project/kolla/config/grafana/dashboards/. /etc/kolla/config/grafana/dashboards/

source ~/kolla-venv/bin/activate
kolla-ansible reconfigure -t grafana -i ~/multinode
```

---

## 6. Monthly Invoicing & Billing Verification (`scripts/invoice.py`)

A reporting script aggregates CloudKitty rating records from Gnocchi to produce itemized client billing invoices for any target month.

### Execution Command:
```bash
cd ~/Cloud-Project
~/kolla-venv/bin/python scripts/invoice.py --month 2026-11 --out invoice.csv
cat invoice.csv
```
