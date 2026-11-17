# Cloud VM Live Migration Files & Automation

Repository containing the CPU stress workload script and complete implementation guide for testing live VM migration on baremetal OpenStack/KVM.

## Contents

- **[`app.py`](app.py)**: Python application that runs a 100% CPU stress workload and serves an auto-updating HTML tracker table recording VM Name, Host Name, and Timestamp.
- **[`LIVE_MIGRATION_STEPS.md`](LIVE_MIGRATION_STEPS.md)**: Full end-to-end instructions for injecting the script into a `.qcow2` image from baremetal, configuring `systemd`, launching in OpenStack, and performing live migration with zero downtime.
