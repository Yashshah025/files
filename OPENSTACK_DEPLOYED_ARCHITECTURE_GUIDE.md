# OpenStack Private Cloud: Complete Deployed Architecture & Component Guide
**Platform:** 4-Node Enterprise OpenStack Cluster (1 Controller + 3 Compute Hypervisors)  
**Deployment Tooling:** Kolla-Ansible (Containerized OpenStack on Docker)  
**Repository Target:** `https://github.com/Yashshah025/files`

---

## 1. High-Level Architecture Overview

We deployed a **production-grade OpenStack private cloud** across 4 bare-metal physical servers orchestrated through **Kolla-Ansible** (OpenStack running in isolated Docker containers):

```
+-----------------------------------------------------------------------------------+
|                        PHYSICAL INFRASTRUCTURE TOPOLOGY                           |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  [ cloud03-controller01 ] (Control Plane Node)                                    |
|   • MariaDB & RabbitMQ (Database & Messaging Backbone)                           |
|   • Keystone, Glance, Horizon (Identity, Image Repository, Web GUI)               |
|   • Nova API, Conductor, Scheduler (Compute Orchestration)                        |
|   • Neutron Server, L3, DHCP, Metadata (Software-Defined Networking)              |
|   • Gnocchi, Ceilometer, CloudKitty (Telemetry, Time-Series & Cloud Billing)      |
|   • Prometheus & Grafana (Infrastructure Observability & Dashboards)              |
|   • GlusterFS Storage Server (/srv/gluster on dedicated 1 TB drive)               |
|                                                                                   |
|         |                                 |                                 |     |
|   VLAN 10 (mgmt)                    VLAN 20 (storage)                 VLAN 30     |
|   10.0.10.x/24                      10.0.20.x/24                    (tunnel VXLAN)|
|         |                                 |                                 |     |
|         v                                 v                                 v     |
|  +-------------------+          +-------------------+          +------------------+
|  | cloud03-compute01 |          | cloud03-compute02 |          | cloud03-compute03|
|  | (Hypervisor 1)    |          | (Hypervisor 2)    |          | (Hypervisor 3)   |
|  | • nova-compute    |          | • nova-compute    |          | • nova-compute   |
|  | • nova-libvirt    |          | • nova-libvirt    |          | • nova-libvirt   |
|  | • neutron-ovs     |          | • neutron-ovs     |          | • neutron-ovs    |
|  | • node-exporter   |          | • node-exporter   |          | • node-exporter  |
|  +-------------------+          +-------------------+          +------------------+
|           \                               |                               /       |
|            +------------------------------+------------------------------+        |
|                                           |                                       |
|                  Shared Storage: /var/lib/nova-shared (GlusterFS)                 |
|                     *Zero-Downtime Live Migration Enabled*                        |
+-----------------------------------------------------------------------------------+
```

---

## 2. In-Depth Component Breakdown & Why Each Was Deployed

---

### Tier 1: Infrastructure Foundations (The Cluster Nervous System)

These services run under the hood; OpenStack cannot function without them.

#### 1. MariaDB (Galera Database)
* **What it does:** The central relational database storing the state of everything in your cloud: user accounts, VM instances, IP address leases, security group rules, network routers, and disk attachments.
* **Why we deployed it:** Every API request (e.g. "create VM", "assign floating IP") is an ACID transaction written to MariaDB.
* **Key Commands:**
  ```bash
  # Check MariaDB container status
  docker ps --filter name=mariadb
  
  # Connect to the database shell
  docker exec -it mariadb mysql -u root -p$(grep database_password /etc/kolla/passwords.yml | awk '{print $2}')
  ```

#### 2. RabbitMQ (Message Broker)
* **What it does:** An asynchronous RPC (Remote Procedure Call) message bus connecting the controller to the hypervisors.
* **Why we deployed it:** When you tell Nova API on the controller to launch a VM, Nova doesn't SSH into Compute 02. Instead, it drops a message into RabbitMQ (`queue: compute.cloud03-compute02`). Compute 02 picks up the job asynchronously, preventing API blocking and timeouts.
* **Key Commands:**
  ```bash
  # Check RabbitMQ cluster status and queues
  docker exec -it rabbitmq rabbitmqctl cluster_status
  docker exec -it rabbitmq rabbitmqctl list_queues
  ```

#### 3. Memcached (In-Memory Key-Value Cache)
* **What it does:** Caches user authentication tokens and web dashboard sessions in RAM.
* **Why we deployed it:** Without Memcached, every single API call would query MariaDB to verify the user's password/token, creating massive database bottlenecks.
* **Key Commands:**
  ```bash
  docker ps --filter name=memcached
  ```

#### 4. Keepalived & HAProxy (Virtual IPs & Reverse Proxy)
* **What it does:** Binds internal Virtual IP `10.0.10.100` (Management) and external Virtual IP `10.14.40.100` (Public API / Horizon).
* **Why we deployed it:** Ensures all compute nodes and users connect to a single unified entry point rather than hardcoding individual physical server IPs.
* **Key Commands:**
  ```bash
  # Check HAProxy frontend/backend status
  docker exec -it haproxy haproxy -c -f /etc/haproxy/haproxy.cfg
  
  # Verify VIPs on network interfaces
  ip -br addr show | grep 100
  ```

---

### Tier 2: Core OpenStack Cloud Services

#### 1. Keystone (Identity & Service Catalog)
* **What it does:** The authentication gateway and yellow-pages of your cloud. It issues cryptographically signed tokens, authenticates projects, users, and roles, and maintains the API endpoint catalog.
* **Why we deployed it:** It is the central authority. Glance, Nova, and Neutron all check with Keystone to verify whether a request is authorized.
* **Key Commands:**
  ```bash
  source ~/kolla-venv/bin/activate
  source /etc/kolla/admin-openrc.sh
  
  openstack endpoint list
  openstack user list
  openstack project list
  ```

#### 2. Glance (Image Service)
* **What it does:** The OS image repository. Stores virtual machine disk templates (like CirrOS, Ubuntu, Debian, CentOS).
* **Why we deployed it:** Backed by our GlusterFS shared storage (`/var/lib/glance-shared`), allowing compute nodes to pull base images instantly without eating controller storage.
* **Key Commands:**
  ```bash
  openstack image list
  openstack image show cirros
  ```

#### 3. Nova (Compute Engine)
* Deployed in modular sub-services:
  * **`nova-api`**: Exposes the REST API for end users and scripts to request VMs.
  * **`nova-scheduler`**: The brain that inspects the CPU, RAM, and disk utilization of Compute 01, 02, and 03 and chooses the best hypervisor to host a new VM.
  * **`nova-conductor`**: Sits between `nova-compute` and MariaDB so hypervisors never have direct SQL database access (critical security barrier).
  * **`nova-compute` & `nova-libvirt`**: Runs directly on each compute node. Translates OpenStack commands into Linux KVM hardware virtualization instructions to start, pause, resize, or destroy virtual machines.
* **Key Commands:**
  ```bash
  # Discover hypervisors into Nova cell v2
  docker exec -t nova_api nova-manage cell_v2 discover_hosts --verbose
  
  # Check compute service and hypervisor availability
  openstack compute service list
  openstack hypervisor list
  openstack hypervisor show cloud03-compute01
  ```

#### 4. Neutron (Software-Defined Networking - SDN)
* **What it does:** Fully virtualized network virtualization:
  * **`neutron-server`**: Controls virtual networks, subnets, routers, and ports.
  * **`neutron-openvswitch-agent`**: Runs on all nodes, programming Open vSwitch kernel bridges (`br-int`, `br-tun`, `br-ex`).
  * **`neutron-dhcp-agent`**: Spawns isolated tenant `dnsmasq` instances to assign private IPs to VMs.
  * **`neutron-l3-agent`**: Virtual router engine managing SNAT (outbound internet access) and DNAT (inbound Floating IPs).
  * **`neutron-metadata-agent`**: Injects SSH keys, passwords, and cloud-init hostnames into booting VMs.
* **Why we deployed it:** Allows tenants to create their own isolated 192.168.50.x networks without overlapping with other tenants or requiring physical switch reconfigurations.
* **Key Commands:**
  ```bash
  openstack network agent list
  openstack network list
  openstack router list
  ```

#### 5. Horizon (Web UI Dashboard)
* **What it does:** The visual browser console (`http://10.14.40.100`).
* **Why we deployed it:** Gives you and your users a graphical, point-and-click interface to launch VMs, view live CPU/RAM usage, create networks, and attach disks.
* **Access Information:**
  * **URL:** `http://10.14.40.100` (or `http://10.0.10.11`)
  * **Domain:** `Default`
  * **Username:** `admin`
  * **Password:** Retrieve with:
    ```bash
    grep 'keystone_admin_password:' /etc/kolla/passwords.yml
    ```

---

### Tier 3: Telemetry, Observability & Cloud Billing

#### 1. Ceilometer (Resource Telemetry)
* **What it does:** Listens to OpenStack event buses and queries libvirt hypervisors every 15 seconds to measure CPU seconds consumed, bytes transmitted, and disk I/O.

#### 2. Gnocchi (Time-Series Metric Storage)
* **What it does:** High-performance time-series database backed by `/var/lib/gnocchi-shared` that aggregates and indexes millions of performance datapoints.
* **Why we deployed it:** Relational databases like MariaDB choke when storing high-frequency metrics. Gnocchi is designed specifically for time-series aggregation.
* **Key Commands:**
  ```bash
  gnocchi status
  gnocchi resource list
  ```

#### 3. CloudKitty (Rating & Billing Engine)
* **What it does:** Connects to Gnocchi metrics and computes real dollar/rupee charges based on pricing rules (e.g. `$0.05/hr for m1.small`, `$0.01/GB for RAM`).
* **Why we deployed it:** Turns raw infrastructure into a commercial **Infrastructure-as-a-Service (IaaS)** platform capable of generating customer invoices.
* **Key Commands:**
  ```bash
  cloudkitty summary get
  ```

#### 4. Prometheus & Grafana (System Monitoring)
* **What it does:** Scrapes system health (`prometheus-node-exporter`, `cadvisor`, `libvirt-exporter`) and renders visual real-time operational dashboards for the cloud administrator.
* **Access Information:**
  * **URL:** `http://10.14.40.100:3000` (or via Horizon / Prometheus port 9090)
  * **Username:** `admin`
  * **Password:** Retrieve with:
    ```bash
    grep 'grafana_admin_password:' /etc/kolla/passwords.yml
    ```

---

### Tier 4: GlusterFS Shared Storage (`/var/lib/nova-shared`)

* **What it does:** Mounts a distributed network filesystem from the Controller’s dedicated 1 TB disk to `/var/lib/nova-shared` across all 3 compute nodes.
* **Why it is critical:** This enables **zero-downtime live migration**. When a running VM moves from Compute 01 to Compute 02, zero disk bytes need to be copied across the network—only CPU registers and RAM states migrate. The virtual disk stays mounted on the shared GlusterFS volume!
* **Key Commands:**
  ```bash
  # Check GlusterFS volume status
  sudo gluster volume status nova
  
  # Check active mount across all nodes
  ansible -i ~/multinode compute -m shell -a "df -h /var/lib/nova-shared" -b
  ```

---

## 3. Summary Checklist of the Operational Private Cloud

* ✅ **1 Controller Node** managing all control plane APIs, databases, message queues, and shared storage.
* ✅ **3 Physical Hypervisors** ready to schedule and run multi-tenant virtual machines.
* ✅ **7 Tagged 802.1Q Isolated VLANs** providing zero network interference between management, storage, APIs, and tenant traffic.
* ✅ **Full Software-Defined Overlay Networking (VXLAN)** with automated DHCP, virtual routers, and floating IPs.
* ✅ **High-Performance Distributed Shared Storage** configured for instant VM live migration.
* ✅ **Enterprise Observability & Billing Stack** tracking CPU, memory, and generating automated monthly cloud usage invoices.
