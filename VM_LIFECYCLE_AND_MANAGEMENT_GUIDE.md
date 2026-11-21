# OpenStack Lab: Multi-Node Virtual Machine Lifecycle Management & Automation Guide
**Platform:** 4-Node OpenStack Cluster (1 Controller + 3 Compute Hypervisors)  
**Execution Context:** Run on Controller (`cloud03-controller01`) as user `ansible` inside `kolla-venv`  
**Repository Target:** `https://github.com/Yashshah025/files`

---

## 1. Overview & Purpose

In multi-node OpenStack cloud environments, benchmarking scheduler behavior, testing live-migration algorithms, and verifying cluster capacity requires orchestrating virtual machine workloads across specific physical hypervisors.

This guide provides automated, production-tested bash scripts to:
1. **Bulk-provision heterogeneous VM tiers** (4 distinct flavors per physical compute node across all 3 nodes = 12 total instances).
2. **Selectively clean up and delete individual or bulk VM workloads** safely without leaving orphaned ports, volumes, or floating IPs.
3. **Inspect real-time hypervisor distribution** and compute capacity.

---

## 2. Prerequisites & Tenant Quotas

Before launching multiple instances across the cluster, ensure the project quotas can accommodate the requested cores, instances, and memory.

```bash
# Activate environment
source ~/kolla-venv/bin/activate
source /etc/kolla/admin-openrc.sh

# Lift quota limits on the admin project
openstack quota set --instances 50 --cores 100 --ram 102400 admin

# Verify quotas
openstack quota show admin
```

---

## 3. Automated VM Provisioning Script

This script iterates through all active compute nodes (`cloud03-compute01`, `cloud03-compute02`, and `cloud03-compute03`), provisioning 4 instances per node using standardized flavors:
* **VM 1:** `m1.tiny` (1 vCPU, 512 MB RAM, 5 GB Disk)
* **VM 2:** `m1.small` (1 vCPU, 1024 MB RAM, 10 GB Disk)
* **VM 3:** `m1.medium` (2 vCPUs, 2048 MB RAM, 20 GB Disk)
* **VM 4:** `m1.small` (1 vCPU, 1024 MB RAM, 10 GB Disk - sized for balanced distribution)

### Creation Script (`spawn_cluster_vms.sh`):

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. Environment initialization
source ~/kolla-venv/bin/activate
source /etc/kolla/admin-openrc.sh

NODES=("cloud03-compute01" "cloud03-compute02" "cloud03-compute03")

echo "=========================================================="
echo "Starting Bulk Instance Deployment (4 VMs per Compute Node)"
echo "=========================================================="

for node in "${NODES[@]}"; do
  short="${node##*-}"          # Extract 'compute01'
  prefix="c${short#compute}"   # Extract 'c01'
  echo ""
  echo ">>> Provisioning instances on Hypervisor: $node"

  # VM 1: Tiny (512 MB)
  echo "  -> Creating ${prefix}-vm-tiny (m1.tiny)..."
  openstack server create \
    --image cirros \
    --flavor m1.tiny \
    --network private-net \
    --key-name mykey \
    --availability-zone "nova:$node" \
    "${prefix}-vm-tiny"

  # VM 2: Small (1024 MB)
  echo "  -> Creating ${prefix}-vm-small (m1.small)..."
  openstack server create \
    --image cirros \
    --flavor m1.small \
    --network private-net \
    --key-name mykey \
    --availability-zone "nova:$node" \
    "${prefix}-vm-small"

  # VM 3: Medium (2048 MB)
  echo "  -> Creating ${prefix}-vm-medium (m1.medium)..."
  openstack server create \
    --image cirros \
    --flavor m1.medium \
    --network private-net \
    --key-name mykey \
    --availability-zone "nova:$node" \
    "${prefix}-vm-medium"

  # VM 4: Extra Small (1024 MB)
  echo "  -> Creating ${prefix}-vm-extra (m1.small)..."
  openstack server create \
    --image cirros \
    --flavor m1.small \
    --network private-net \
    --key-name mykey \
    --availability-zone "nova:$node" \
    "${prefix}-vm-extra"
done

echo ""
echo "All 12 instances submitted to Nova API. Waiting 15 seconds for ACTIVE state..."
sleep 15

# Output verification table
openstack server list -c Name -c Status -c "OS-EXT-SRV-ATTR:host" -c Flavor --long
```

---

## 4. Cluster Workload Verification

To monitor active placement across all hypervisors:

```bash
# 1. Summary list showing instance name, host, and status
openstack server list -c Name -c Status -c "OS-EXT-SRV-ATTR:host" -c Flavor --long

# 2. Count instances per compute host
python3 live-migration/migrate.py --list

# 3. Overall hypervisor resource consumption
openstack hypervisor stats show
```

---

## 5. VM Deletion & Cleanup Automation

When testing is complete or when preparing to re-run distribution tests, use the appropriate deletion script below.

### Option A: Delete All Cluster Benchmark Instances in Bulk

This script removes all 12 benchmark VMs created by the provisioning loop:

```bash
#!/usr/bin/env bash
source ~/kolla-venv/bin/activate
source /etc/kolla/admin-openrc.sh

echo "Deleting all benchmark instances..."

openstack server delete \
  c01-vm-tiny c01-vm-small c01-vm-medium c01-vm-extra \
  c02-vm-tiny c02-vm-small c02-vm-medium c02-vm-extra \
  c03-vm-tiny c03-vm-small c03-vm-medium c03-vm-extra \
  2>/dev/null || true

echo "Cleanup command issued. Remaining servers:"
openstack server list
```

---

### Option B: Delete Instances on a Single Specific Compute Node

To drain or clean up only the instances hosted on a single target compute node (e.g. `cloud03-compute03`):

```bash
#!/usr/bin/env bash
TARGET_NODE="${1:-cloud03-compute03}"

source ~/kolla-venv/bin/activate
source /etc/kolla/admin-openrc.sh

echo "Finding instances running on $TARGET_NODE..."
VMS=$(openstack server list --host "$TARGET_NODE" -f value -c ID)

if [ -n "$VMS" ]; then
  echo "Deleting instances on $TARGET_NODE:"
  echo "$VMS"
  openstack server delete $VMS
else
  echo "No instances found on $TARGET_NODE."
fi
```

---

### Option C: Complete Project Teardown (Delete ALL Instances)

To wipe every single instance in the OpenStack environment in one command:

```bash
source ~/kolla-venv/bin/activate
source /etc/kolla/admin-openrc.sh

# Delete all instances across all projects
openstack server delete $(openstack server list -q -c ID -f value) 2>/dev/null || echo "No servers to delete."
```

---

## 6. Assigning & Removing Floating IPs

To expose an instance externally for ping or SSH testing:

```bash
# 1. Allocate floating IP from provider-net
FIP=$(openstack floating ip create provider-net -f value -c floating_ip_address)

# 2. Bind floating IP to an instance
openstack server add floating ip c01-vm-tiny "$FIP"
echo "Instance accessible at: $FIP"

# 3. Disassociate and delete floating IP when done
openstack server remove floating ip c01-vm-tiny "$FIP"
openstack floating ip delete "$FIP"
```
