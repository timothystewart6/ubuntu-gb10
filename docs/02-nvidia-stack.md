# 02 - NVIDIA Software Stack

## Overview

This guide installs the NVIDIA GPU driver, CUDA toolkit, and supporting packages
on Ubuntu Server 24.04 (arm64) using NVIDIA's official repositories. The approach
follows the DGX OS 7 "Customizing Ubuntu Installation with DGX Software" guide,
using the **DGX Spark** / ARM64 package variants since the ASUS GX10 is a GB10
Grace Blackwell partner system.

References:

- <https://docs.nvidia.com/dgx/dgx-os-7-user-guide/installing_on_ubuntu.html>
- <https://docs.nvidia.com/dgx/dgx-spark/release-notes.html>

### Architecture Notes for GB10 / Unified Memory

The GB10 Grace Blackwell Superchip uses a **unified memory architecture (UMA)**.
There is no dedicated VRAM - the Blackwell GPU and the 20-core Grace CPU share
the same 128 GB of LPDDR5x DRAM via NVLink-C2C.

This has two important implications:

1. `nvidia-smi` will display **`Memory-Usage: Not Supported`** in the memory
   field. This is **expected and normal** on iGPU/UMA platforms - not an error.
2. `cudaMemGetInfo` may report less available memory than is actually usable,
   because it does not account for pages that could be reclaimed from swap.
   Use `/proc/meminfo` (`MemAvailable` + `SwapFree`) for accurate estimates.

### Target Software Versions

| Component           | Version        |
|---------------------|----------------|
| NVIDIA GPU Driver   | 580.167.08     |
| NVIDIA CUDA Toolkit | 13.0.2         |
| Kernel              | 6.17.0-1021-nvidia (HWE) |

> The ASUS GX10 is a GB10 partner system. DGX Spark Founders Edition versions
> are used as the reference baseline. Partner systems may trail by one release.

---

## Prerequisites

- Ubuntu Server 24.04 LTS (arm64) installed and updated - see [01-ubuntu-install.md](01-ubuntu-install.md)
- Internet access from the host
- `sudo` access

---

## Step 1 - Enable NVIDIA Repositories

This downloads a tarball from NVIDIA that installs:

- APT source list files into `/etc/apt/`
- GPG keyrings into `/usr/share/keyrings/`
- Package pinning/preferences files

```bash
# ARM64 systems (GB10 / DGX Spark / ASUS GX10)
curl https://repo.download.nvidia.com/baseos/ubuntu/noble/arm64/dgx-repo-files.tgz \
  | sudo tar xzf - -C /
```

Verify the repo files landed correctly:

```bash
ls /etc/apt/sources.list.d/
```

Expected files (none are named with "nvidia" - that grep will return nothing):

```terminal
cuda-compute-repo.sources
dgx.sources
doca-bos8-latest.sources
nvhpc.sources
ai-workbench-desktop.sources
```

Keyrings:

```bash
ls /usr/share/keyrings/ | grep -E 'cuda|dgx|doca|mellanox|nvidia'
```

---

## Step 2 - Update Package Database

```bash
sudo apt update
```

---

## Step 3 - Upgrade All Packages

```bash
sudo apt upgrade -y
```

---

## Step 4 - Install Core NVIDIA System Packages

These metapackages bundle DGX-derived performance configurations, tools, and
drivers. They are built for DGX Spark (ARM64) and work correctly on GB10
partner hardware.

### Core system package - required for GPU performance and platform tuning

```bash
sudo apt install -y nvidia-system-core
```

### System utilities - includes NVSM health monitoring, cachefilesd, nvidia-motd

```bash
sudo apt install -y nvidia-system-utils
```

### Development and extra tools - includes automake, build-essential, vim

> **Note:** `nvidia-system-extra` pulls in `docker-ce` and `nvidia-container-toolkit` as
> dependencies. If you want to control Docker installation separately (recommended
> - see [03-docker-gpu.md](03-docker-gpu.md)), skip the command below and move on.

```bash
sudo apt install -y nvidia-system-extra
```

> **Desktop/GUI:** Do NOT install `nvidia-system-station` unless you want a full
> GNOME desktop environment. This is a server - skip it.

### Linux perf tools - ARM64 / DGX Spark variant

```bash
sudo apt install -y linux-tools-nvidia-hwe-24.04
```

### NVIDIA peermem loader - required for GPUDirect RDMA over ConnectX-7

```bash
sudo apt install -y nvidia-peermem-loader
```

---

## Step 5 - Install the HWE Kernel

The DGX Spark runs the NVIDIA/Ubuntu HWE kernel, not the standard generic kernel.
This provides better support for the Grace Blackwell SoC and NVLink-C2C.

```bash
# ARM64 / DGX Spark HWE kernel
sudo apt install -y linux-nvidia-hwe-24.04
```

Reboot into the new kernel before installing the driver:

```bash
sudo reboot
```

After reboot, confirm the kernel version:

```bash
uname -r
# Expected: something like 6.17.x-nvidia-...
```

---

## Step 6 - Install the GPU Driver

### 6a - Confirm available driver versions

```bash
sudo apt update
sudo apt list 'nvidia-driver*open' 2>/dev/null
```

Current production version for Blackwell is **580** (e.g. `nvidia-driver-580-open`).
Blackwell architecture (GB10) **requires** the 580 family or newer.

### 6b - Install the driver pinning package

For 580+ family drivers, the pinning package must be installed first. It locks
all related packages to a consistent version set.

```bash
sudo apt install -y nvidia-driver-pinning-580
```

### 6c - Install the open GPU kernel modules and supporting packages

The open GPU kernel modules are required for Blackwell architecture.

> Do NOT install `nvidia-fabricmanager` - that is for DGX systems with NVSwitch
> hardware only. The GX10 does not have NVSwitch.

> **Note:** `nvidia-modprobe` may need to be downgraded to match the 580 family
> version. Add `--allow-downgrades` to handle this automatically.

```bash
sudo apt install -y --allow-downgrades \
  nvidia-driver-580-open \
  libnvidia-nscq \
  nvidia-modprobe \
  datacenter-gpu-manager-4-cuda13 \
  nv-persistence-mode
```

### 6d - Enable persistence daemon and DCGM

```bash
sudo systemctl enable --now nvidia-persistenced nvidia-dcgm
```

### 6e - Reboot

```bash
sudo reboot
```

---

## Step 7 - Verify GPU Driver

After reboot:

```bash
nvidia-smi
```

**Expected output on GB10 (UMA platform):**

```terminal
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 580.167.08             Driver Version: 580.167.08     CUDA Version: 13.0     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GB10                    On  |   0000000F:01:00.0  On |                  N/A |
| N/A   41C    P8              5W /  N/A  | Not Supported          |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
```

> **`Memory-Usage: Not Supported` is normal and expected.** The GB10 uses unified
> memory - there is no separate VRAM pool to report. This is a known behaviour
> documented by NVIDIA for all iGPU/UMA platforms.

Verify the kernel module loaded:

```bash
lsmod | grep nvidia
```

---

## Step 8 - Install CUDA Toolkit

The CUDA toolkit provides `nvcc`, libraries, and headers for GPU development.
It is separate from the driver.

```bash
# Match CUDA 13.x for driver 580
sudo apt install -y cuda-toolkit-13-0
```

Verify:

```bash
nvcc --version
```

Add CUDA to PATH permanently:

```bash
echo 'export PATH=/usr/local/cuda/bin:$PATH' | sudo tee /etc/profile.d/cuda.sh
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' | sudo tee -a /etc/profile.d/cuda.sh
source /etc/profile.d/cuda.sh
```

---

## Unified Memory Debugging Tips

Because `cudaMemGetInfo` underreports on UMA systems, use `/proc/meminfo` for
a realistic picture of available memory:

```bash
# See actual available system memory (includes what GPU can use)
grep -E 'MemTotal|MemAvailable|SwapFree' /proc/meminfo
```

If a CUDA workload fails with out-of-memory errors despite seemingly having free
memory, flush the page cache first:

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

Then retry the workload.

---

## Next Step

Continue to [03-docker-gpu.md](03-docker-gpu.md) for Docker + NVIDIA Container
Toolkit, or [04-doca-ofed.md](04-doca-ofed.md) for ConnectX-7 networking setup.
