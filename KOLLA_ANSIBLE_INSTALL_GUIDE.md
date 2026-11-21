# OpenStack Lab: Kolla-Ansible Installation Guide (`kolla/install.sh`)
**Platform:** 4-Node OpenStack Cluster (1 Controller + 3 Compute Nodes)  
**Script:** `kolla/install.sh`  
**Execution Context:** Run on Controller (`cloud03-controller01`) after `ansible/site.yml` succeeds

---

## Overview

`kolla/install.sh` prepares the Controller node to orchestrate the OpenStack containerized deployment. It transforms the node into an active Kolla deploy host by setting up Python environments, fetching official OpenStack tools, generating cryptographic credentials, and preparing the master multi-node inventory.

It performs **8 major automated steps**:

---

### 1. Installs System & C Build Dependencies
Runs `apt-get` to install system packages required to compile Python modules:
* `git`, `python3-venv`, `python3-dev`, `python3-yaml`, `gcc`, `libffi-dev`, `libssl-dev`, `libdbus-glib-1-dev`.

### 2. Validates Inventory Integrity
An embedded Python script checks `kolla/multinode-head.ini` against `ansible/inventory.yml`:
* Verifies that the hosts under `[control]`, `[network]`, `[monitoring]`, `[storage]`, and `[compute]` match between both files so there are no discrepancies.

### 3. Creates an Isolated Virtual Environment (`~/kolla-venv`)
Creates a dedicated Python virtualenv to keep the deployment isolated from the host OS:
* Installs **Kolla-Ansible** (from official OpenStack OpenDev repository).
* Installs OpenStack CLI tools: `python-openstackclient`, `gnocchiclient`, `python-cloudkittyclient`, `openstacksdk`, and the `docker` SDK.

### 4. Installs Ansible Collections (`kolla-ansible install-deps`)
* Creates `/etc/kolla/`.
* Runs `kolla-ansible install-deps` which uses `ansible-galaxy` to install required collections (e.g. `community.docker`, `ansible.posix`).

### 5. Generates Secure Passwords (`kolla-genpwd`)
* Populates `/etc/kolla/passwords.yml` with cryptographically secure random passwords for all internal services:
  * MariaDB root & service passwords
  * RabbitMQ credentials
  * Keystone `admin` password
  * Service tokens for Nova, Neutron, Glance, Horizon secret keys, etc.
* *(Note: It only fills empty values; it never overwrites existing passwords).*

### 6. Writes Cluster Configuration (`/etc/kolla/globals.yml` & `/etc/kolla/config`)
* Deploys our tuned `globals.yml` (specifying network interfaces `mgmt`, `api`, `tunnel`, `provider`, container images, enabled services).
* Deploys custom service configs to `/etc/kolla/config/` (Nova compute virtualization settings, Glance GlusterFS storage integration, Prometheus scrape targets).

### 7. Builds the Master Deployment Inventory (`~/multinode`)
* Merges our host definitions (`multinode-head.ini`) with Kolla's stock service inheritance graph.
* Sets `ansible_user=ansible`.
* Uses `ssh-keyscan` to automatically register host keys into `~/.ssh/known_hosts` so Ansible never gets blocked by interactive confirmation prompts.

### 8. Audits Service Placement & Runs Health Check Ping
* Inspects the generated inventory to ensure core services (`glance-api`, `gnocchi`, `valkey`, `prometheus`, `grafana`) map to the controller.
* Executes `ansible -i ~/multinode all -m ping` across all nodes to confirm end-to-end SSH and Python readiness for deployment.
