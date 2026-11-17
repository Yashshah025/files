# Live VM Migration Guide: Automated CPU Workload on Boot

A complete guide for injecting a CPU-heavy process and live HTML migration tracker into a `.qcow2` image from a baremetal host, launching it on OpenStack, and performing live migration with zero downtime.

---

## 1. Overview & Architecture

### What is Live VM Migration?
Live migration allows moving a running Virtual Machine (VM) between two physical baremetal hypervisors (e.g. `cloud03-compute01` &rarr; `cloud03-compute02`) without turning off the VM, disconnecting active network sockets, or losing application state.

### Why Run a CPU-Heavy Workload?
Migrating an idle VM is trivial because its RAM is static. In production environments, VMs run heavy databases, APIs, or computational workloads. When CPUs run at 100%, RAM pages are modified at high speed (**"dirty memory"**). This script forces maximum CPU usage (100% across all cores) to test migration performance under realistic, high-pressure conditions.

### What `app.py` Does:
1. **CPU Saturation**: Runs continuous SHA-256 cryptographic hashing loops across all detected vCPUs to pin CPU load at 100%.
2. **Auto-Discovery**: Queries OpenStack metadata (`169.254.169.254`) and system hostnames to detect VM Name and the current Baremetal Host.
3. **Live HTML Tracker**: Hosts an HTTP server on port 80 serving an auto-refreshing dashboard that records:
   - **VM Name**
   - **Host Name** (the physical hypervisor)
   - **Timestamp (UTC)**

---

## 2. Step-by-Step Implementation Guide

Run these steps on your **OpenStack baremetal controller node** (e.g., `cloud03-controller01`).

### Phase 1: Environment Setup & Download Base Image

```bash
# 1. Activate OpenStack credentials
source ~/kolla-venv/bin/activate
source /etc/kolla/admin-openrc.sh

# 2. Install virt-customize (libguestfs-tools) to modify qcow2 images directly on baremetal
sudo apt update
sudo apt install -y libguestfs-tools

# 3. Download the official Ubuntu 22.04 LTS cloud image
wget https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img -O ubuntu-workload.qcow2
```

---

### Phase 2: Inject Script & Systemd Service into the QCOW2 Image

#### 1. Download `app.py`:
```bash
wget https://raw.githubusercontent.com/Yashshah025/files/main/app.py -O app.py
```

#### 2. Create the Systemd service file:
```bash
cat << 'EOF' > cpu-workload.service
[Unit]
Description=CPU Heavy Workload and Live Migration Tracker
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cpu-workload
Environment="PORT=80"
Environment="APPEND_INTERVAL=5"
Environment="CPU_WORKERS=0"
Environment="CPU_LOAD_PERCENT=100"
Environment="HTML_FILE_PATH=/opt/cpu-workload/data/index.html"
ExecStart=/usr/bin/python3 /opt/cpu-workload/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

#### 3. Inject both into `ubuntu-workload.qcow2`:
```bash
virt-customize -a ubuntu-workload.qcow2 \
  --root-password password:ubuntu \
  --run-command "mkdir -p /opt/cpu-workload/data" \
  --copy-in app.py:/opt/cpu-workload/ \
  --chmod 0755:/opt/cpu-workload/app.py \
  --copy-in cpu-workload.service:/etc/systemd/system/ \
  --run-command "systemctl enable cpu-workload.service"
```

---

### Phase 3: Register Image & Configure Security Groups

#### 1. Upload the customized image to Glance:
```bash
openstack image create "ubuntu-cpu-tracker" \
  --file ubuntu-workload.qcow2 \
  --disk-format qcow2 \
  --container-format bare \
  --public
```

#### 2. Open HTTP (Port 80) and ICMP (Ping) in the Security Group:
```bash
openstack security group rule create --proto tcp --dst-port 80 default || true
openstack security group rule create --proto icmp default || true
```

---

### Phase 4: Launch the VM on Compute Node A

#### 1. Launch the VM pinned to `cloud03-compute01`:
```bash
openstack server create \
  --image ubuntu-cpu-tracker \
  --flavor m1.medium \
  --network private-net \
  --availability-zone "nova:cloud03-compute01" \
  --wait cpu-tracker-vm
```

#### 2. Assign a Floating IP:
```bash
FLOATING_IP=$(openstack floating ip create provider-net -f value -c floating_ip_address)
openstack server add floating ip cpu-tracker-vm $FLOATING_IP

echo "============================================="
echo "VM is ready! Open this URL in your browser:"
echo "http://${FLOATING_IP}/"
echo "============================================="
```

---

### Phase 5: Verification & Live Migration

#### 1. View Live Web Dashboard:
Open `http://<FLOATING_IP>/` in your browser.
- You will see the auto-updating table recording `VM Name`, `Host Name`, and `Timestamp` every 5 seconds.

#### 2. Verify CPU Saturation on Baremetal:
SSH into `cloud03-compute01` and run `top`.
- The QEMU/KVM process will show 100% CPU usage across all assigned vCPUs.

#### 3. Perform Live Migration:
From the controller node, migrate the VM to `cloud03-compute02`:
```bash
openstack server migrate --live-migration --host cloud03-compute02 cpu-tracker-vm
```
*(Or use CloudShift scheduler: `python3 live-migration/migrate.py cpu-tracker-vm --to cloud03-compute02`)*

#### 4. Observe Zero Downtime:
Keep `http://<FLOATING_IP>/` open in your browser:
- The timestamps will continue ticking without interruption.
- The **Host Name** column will transition seamlessly from `cloud03-compute01` to `cloud03-compute02`.
