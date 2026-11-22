# 📚 CloudShift: Complete Architecture, Automation & Deployment Documentation

Comprehensive technical documentation, step-by-step operational runbooks, stress workload scripts, and architecture deep dives for the **CloudShift 4-Node OpenStack Private Cloud Lab** (1 Controller + 3 Compute Hypervisors).

> **Main Implementation Repository:** [**Yashshah025/CloudShift**](https://github.com/Yashshah025/CloudShift)

---

## 🧭 Repository Contents & Guides

This repository serves as the centralized knowledge base and asset repository for the entire lifecycle of the CloudShift deployment—from bare-metal hardware and physical switch provisioning to containerized OpenStack orchestration, custom VM stress workloads, and autonomous live migration.

### 📖 Architectural & Operational Runbooks

| Guide | Focus Area | Description |
|:---|:---|:---|
| [**SWITCH_CONFIGURATION_GUIDE.md**](SWITCH_CONFIGURATION_GUIDE.md) | Physical Networking & L2 | D-Link DGS-1210-28 L2 switch setup, 802.1Q tagged VLANs (10–70), PVID 1 untagged management, RSTP spanning tree, and per-port wiring mapping. |
| [**CLUSTER_BOOTSTRAP_GUIDE.md**](CLUSTER_BOOTSTRAP_GUIDE.md) | Bare-Metal & SSH | Controller & compute node bootstrap, ED25519 cluster key generation, per-node username distribution, and passwordless sudo setup. |
| [**PREFLIGHT_VERIFICATION_GUIDE.md**](PREFLIGHT_VERIFICATION_GUIDE.md) | Validation & Prechecks | 8-point preflight validation: hostname alignment, kernel module checks, interface states, Wi-Fi/uplink reachability, and memory sanity checks. |
| [**STORAGE_ARCHITECTURE_GUIDE.md**](STORAGE_ARCHITECTURE_GUIDE.md) | Distributed Storage | Secondary disk partitioning (`/dev/sdb`), XFS filesystem tuning, distributed GlusterFS volumes (`nova`, `glance`, `gnocchi`), and immutable mount protection (`+i`). |
| [**SITE_PROVISIONING_AND_VERIFICATION_GUIDE.md**](SITE_PROVISIONING_AND_VERIFICATION_GUIDE.md) | Network Fabric & Gateways | Netplan automated VLAN carving, Keepalived VRRP virtual IP failover, NAT egress masquerading, cluster DNS (`dnsmasq`), and full-mesh connectivity verification. |
| [**KOLLA_ANSIBLE_INSTALL_GUIDE.md**](KOLLA_ANSIBLE_INSTALL_GUIDE.md) | Kolla Control Plane | Python virtual environment setup (`kolla-venv`), Kolla-Ansible installation, cryptographic secret generation (`kolla-genpwd`), and dynamic inventory generation. |
| [**OPENSTACK_DEPLOYED_ARCHITECTURE_GUIDE.md**](OPENSTACK_DEPLOYED_ARCHITECTURE_GUIDE.md) | Containerized Services | Deep dive into deployed OpenStack services: MariaDB Galera, RabbitMQ, Keystone, Nova, Neutron (OVS/VXLAN), Glance, Horizon, Ceilometer, Gnocchi, and CloudKitty. |
| [**POST_DEPLOYMENT_RESOURCES_AND_LIVE_MIGRATION_GUIDE.md**](POST_DEPLOYMENT_RESOURCES_AND_LIVE_MIGRATION_GUIDE.md) | Day-2 Ops & Verification | Cloud network & flavor setup (`01-cloud-setup.sh`), Prometheus metric exporters, CloudKitty billing rules, and manual/autonomous zero-downtime VM live migration. |
| [**VM_LIFECYCLE_AND_MANAGEMENT_GUIDE.md**](VM_LIFECYCLE_AND_MANAGEMENT_GUIDE.md) | Workload Orchestration | Automated bulk instance provisioning (4 VMs per hypervisor), floating IP allocation, selective/per-host/full teardown routines, and quota management. |
| [**LIVE_MIGRATION_STEPS.md**](LIVE_MIGRATION_STEPS.md) | Zero-Downtime Migration | End-to-end instructions for injecting the stress workload into `.qcow2` images, `systemd` daemon setup, instance launching, and live-migration verification. |

---

### ⚙️ Automation & Workload Scripts

* **[`app.py`](app.py)**: Multi-threaded Python application designed for live migration verification. Spawns continuous CPU-bound stress workers to generate realistic hypervisor load while hosting a lightweight HTTP service that dynamically records and displays instance hostname, hypervisor location, and timestamp tracking for zero packet-loss validation.

---

## 🏛️ Physical & Logical Architecture

```
                         Uplink / Internet (USB Tethering 10.72.247.x)
                                              │
                                   ┌──────────────────────┐
                                   │ cloud03-controller01 │
                                   │ • Control Plane APIs │
                                   │ • GlusterFS Storage  │
                                   │ • Keepalived Gateway │
                                   └──────────────────────┘
                                              │
                          D-Link DGS-1210-28 Managed Switch
                    Trunk Ports 1-4: 802.1Q Tagged VLANs (10 - 70)
                                              │
            ┌─────────────────────────────────┼─────────────────────────────────┐
            │                                 │                                 │
  ┌───────────────────┐             ┌───────────────────┐             ┌───────────────────┐
  │ cloud03-compute01 │             │ cloud03-compute02 │             │ cloud03-compute03 │
  │ (Port 2: .21)     │             │ (Port 3: .22)     │             │ (Port 4: .23)     │
  │ • nova-compute    │             │ • nova-compute    │             │ • nova-compute    │
  │ • nova-libvirt    │             │ • nova-libvirt    │             │ • nova-libvirt    │
  │ • neutron-ovs     │             │ • neutron-ovs     │             │ • neutron-ovs     │
  └───────────────────┘             └───────────────────┘             └───────────────────┘
            │                                 │                                 │
            └─────────────────────────────────┼─────────────────────────────────┘
                                              │
                        Shared Storage Volume: /var/lib/nova-shared (GlusterFS)
```

---

## 🌐 Network VLAN Segmentation

| VLAN Tag | Interface | Subnet Range | Gateway / VIP | Primary Function |
|:---|:---|:---|:---|:---|
| **VLAN 10** | `mgmt` | `10.0.10.0/24` | `10.0.10.100` (VIP) | Internal APIs, Galera, RabbitMQ, Nova RPC & Live Migration |
| **VLAN 20** | `storage` | `10.0.20.0/24` | — | Dedicated GlusterFS distributed storage network |
| **VLAN 30** | `tunnel` | `10.11.10.0/24` | — | Neutron VXLAN tenant overlay networks |
| **VLAN 40** | `api` | `10.14.40.0/24` | `10.14.40.100` (VIP) | Public API endpoints, Horizon Dashboard & Grafana UI |
| **VLAN 50** | `egress` | `10.12.0.0/24` | `10.12.0.1` (VRRP) | Compute nodes default route & outbound NAT masquerade |
| **VLAN 60** | `provider` | `172.24.4.0/24` | `172.24.4.1` (br-ex) | External floating IP pool (`172.24.4.100` – `.199`) |
| **VLAN 70** | `dns` | `10.0.70.0/24` | `10.0.70.11` | Cluster-wide internal DNS resolution (`cloud03.lab`) |
| **Native 1** | `eno1` | `192.168.0.0/24` | — | Out-of-band management & initial host bootstrap |

---

## ⚡ Key Architectural Capabilities

* **High-Availability Gateway:** Keepalived VRRP active-backup router on VLAN 50 with health probes tracking uplink internet reachability.
* **Shared Storage & Zero Downtime:** Direct GlusterFS mount at `/var/lib/nova-shared` enabling memory-only VM live migrations across compute nodes with zero packet loss.
* **Dynamic Load Balancing:** Automated scheduling agent (`scheduler.py`) ingesting Prometheus hypervisor metrics to prevent CPU hot-spotting.
* **Autonomous Billing & Invoicing:** Metric collection through Ceilometer & Gnocchi, rated via CloudKitty pricing rules, and exported into itemized monthly CSV invoices.
* **Infrastructure as Code:** Fully repeatable automation across physical network switches, host Netplan configs, systemd daemons, and Kolla-Ansible container groups.

---

## 🔗 Related Repositories

* **Deployment Code & Playbooks:** [https://github.com/Yashshah025/CloudShift](https://github.com/Yashshah025/CloudShift)
* **Upstream Project:** [https://github.com/Aagam41/CloudShift](https://github.com/Aagam41/CloudShift)
