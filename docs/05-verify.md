# 05 - Post-Install Verification

## Overview

Run through this checklist after completing the full installation to confirm
all components are working correctly.

### GB10 / UMA Platform Notes Before You Start

The ASUS GX10 uses unified memory architecture (UMA). Two behaviours are
**expected and normal** - do not treat them as failures:

| What you see | Why | Action needed |
|---|---|---|
| `nvidia-smi` shows `Memory-Usage: Not Supported` | No dedicated VRAM on iGPU/UMA platforms | None - this is correct |
| `cudaMemGetInfo` reports less than 128 GB free | Does not count reclaimable swap pages | Use `/proc/meminfo` for accurate view |

### Server vs Desktop: Why minimal install matters

On GB10 the GPU and CPU share the same physical memory pool. Any memory consumed
by OS processes - including a desktop environment - directly reduces the memory
available to your LLMs. Measured idle footprint on identically-specced GX10 units:

| Config | Used at idle | Available for models |
|--------|-------------|----------------------|
| gb10-1 (DGX OS with GNOME desktop, idle) | ~4.7 GiB | ~116 GiB |
| gb10-1 (DGX OS with GNOME desktop, apps open) | ~5.8 GiB | ~115 GiB |
| gb10-1 (Ubuntu Server minimized, no desktop) | ~3.0 GiB | **~118 GiB** |

The desktop (Xorg + gnome-shell + gnome-remote-desktop) consumes ~340 MB of GPU
memory alone, plus additional system RAM. On a 128 GB system this is small but
it compounds under load. For a dedicated inference server, the minimal install
is the right choice.

---

## Measured Results

Results measured on an ASUS Ascent GX10 with identical hardware across both configurations.

### Memory Footprint

| Configuration | RAM Used (idle) | RAM Available for Models |
|---|---|---|
| DGX OS 7 + GNOME desktop (idle) | ~4.7 GiB | ~116 GiB |
| DGX OS 7 + GNOME desktop (apps open) | ~5.8 GiB | ~115 GiB |
| **Ubuntu Server 24.04 minimized (this guide)** | **2.9 GiB** | **118 GiB** |

Savings vs. DGX OS idle: **~1.8 GiB** recovered for model use.

### CPU Frequency Scaling

The GB10 Grace CPU has two core clusters with different max frequencies:

| Cluster | Cores | Max Frequency |
|---|---|---|
| Efficiency (E-cores) | 10 | 2808 MHz |
| Performance (P-cores) | 10 | 3900 MHz |

Dynamic scaling is fully functional. Measured with `schedutil` governor:

| State | E-core freq | P-core freq |
|---|---|---|
| Idle | ~338 MHz | ~1378 MHz |
| Under full CPU load | 2808 MHz | 3900 MHz |
| 3 seconds after load ends | ~338 MHz | ~1378 MHz |

See [06-optimizations.md](06-optimizations.md) to switch between `schedutil` and `performance`.

### Power Draw

Measured at the wall with a smart plug (idle, no active workload):

| Configuration | Idle Power |
|---|---|
| DGX OS 7 + GNOME desktop | ~45-50 W |
| **Ubuntu Server 24.04 minimized (this guide)** | **~40-45 W** |

> The ConnectX-7 high-speed networking is a major idle power consumer. This cannot
> be reduced meaningfully through software because the PCIe link does not support
> ASPM and the mlx5 driver keeps the device active. The savings vs. DGX OS come
> from eliminating the display server and desktop services, not from the NIC.

### DGX OS vs. Ubuntu Server - Feature Comparison

| Feature | DGX OS 7 | Ubuntu Server 24.04 (this guide) |
|---|---|---|
| Base OS | Ubuntu 24.04 | Ubuntu 24.04 |
| GNOME desktop | Included | Not installed |
| NVIDIA driver | Pre-installed (closed) | Installed manually (open modules) |
| CUDA toolkit | Pre-installed | Installed manually |
| nvidia-smi / DCGM | Pre-installed | Installed manually |
| Docker + NVIDIA CTK | Pre-installed | Installed manually |
| NCCL | Pre-installed | Pre-installed via package |
| ConnectX-7 DOCA-OFED | Pre-installed | Installed manually |
| Secure Boot | Enabled | Enabled (MOK enrollment required) |
| RAM available at idle | ~116 GiB | 118 GiB |
| Idle power draw | ~45-50 W | ~40-45 W |
| Update cadence | NVIDIA-controlled | Standard Ubuntu LTS |
| CPU governor | performance (pinned to max) | performance (pinned to max) |

---

## System Basics

```bash
# OS version - should be Ubuntu 24.04
lsb_release -a

# Kernel version - should be 6.17.x-nvidia
uname -r

# Hostname
hostname -f

# Network connectivity
ping -c 3 8.8.8.8

# Disk space
df -h

# Memory
free -h
```

---

## NVIDIA GPU Driver

```bash
# Show GPU info with driver and CUDA version
nvidia-smi
```

> **Expected on GB10:** `Memory-Usage: Not Supported` in the memory field.
> Persistence-Mode should show `On`. This is the normal output for a UMA platform.

```terminal
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 580.167.08   Driver Version: 580.167.08   CUDA Version: 13.0               |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|=========================================+========================+======================|
|   0  NVIDIA GB10                    On  | 0000000F:01:00.0   Off |                  N/A |
| N/A   40C    P8               5W /  N/A |       Not Supported    |   0%      Default    |
+-----------------------------------------+------------------------+----------------------+
```

```bash
# Show GPU topology (useful if linking two GX10 units)
nvidia-smi topo -m

# Check that persistence mode is ON
nvidia-smi --query-gpu=name,persistence_mode --format=csv,noheader

# Verify open kernel module is loaded
lsmod | grep nvidia

# Check driver version
cat /proc/driver/nvidia/version
```

## Actual Memory Available (UMA)

Use `/proc/meminfo` for a real picture of memory on the GB10:

```bash
grep -E 'MemTotal|MemAvailable|SwapFree' /proc/meminfo
```

Expected: `MemTotal` near 128 GB (131072 MB range).

---

## DCGM (Data Center GPU Manager)

```bash
# Check DCGM service status
sudo systemctl status nvidia-dcgm

# Run a quick health check on all GPUs
dcgmi health -g 0 -c

# Run a short diagnostic (level 1 = quick, level 3 = full)
dcgmi diag -r 1
```

---

## CUDA Toolkit

```bash
# CUDA compiler version (full path required if cuda.sh not sourced yet)
/usr/local/cuda/bin/nvcc --version

# Or if PATH already includes /usr/local/cuda/bin:
nvcc --version

# CUDA library path
ls /usr/local/cuda/lib64/libcudart*
```

---

## NCCL

NCCL (NVIDIA Collective Communication Library) is installed as a system package.
The `nccl-tests` suite built from source is the standard way to verify it.

```bash
# Confirm package version
dpkg -l libnccl2

# Build nccl-tests if not already built (one-time)
git clone https://github.com/NVIDIA/nccl-tests.git ~/nccl-tests
cd ~/nccl-tests
CUDA_HOME=/usr/local/cuda MPI_HOME=/usr/lib/aarch64-linux-gnu/openmpi make -j MPI=1
```

Single-node all_reduce smoke test:

```bash
LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:/usr/local/cuda/lib64:$LD_LIBRARY_PATH \
  ~/nccl-tests/build/all_reduce_perf -b 8M -e 1G -f 2 -g 1
```

Expected output ends with:

```terminal
# Out of bounds values : 0 OK
# Avg bus bandwidth    : 0
```

`#wrong = 0` on every row confirms NCCL is functioning correctly. Bus bandwidth
shows `0` for a single-GPU run (expected - bus bandwidth is only meaningful for
multi-node tests).

---

## Docker + NVIDIA Container Toolkit

```bash
# Docker version
docker version

# NVIDIA Container Toolkit version
nvidia-ctk --version

# Confirm the runtime is configured
cat /etc/docker/daemon.json

# Test GPU access inside a container
docker run --gpus=all --rm nvcr.io/nvidia/cuda:12.6.2-base-ubuntu24.04 nvidia-smi
```

---

## Services Checklist

```bash
# Check all NVIDIA-related services
for svc in nvidia-persistenced nvidia-dcgm docker; do
  echo -n "$svc: "
  systemctl is-active $svc
done
```

All should print `active`.

---

## Quick Smoke Test - Run a GPU Workload in a Container

Run the CUDA `nbody` sample to exercise actual GPU compute:

```bash
docker run --gpus=all --rm nvcr.io/nvidia/cuda:12.6.2-devel-ubuntu24.04 \
  bash -c "apt-get install -y cuda-samples-12-6 -qq && \
           /usr/local/cuda/samples/5_Domain_Specific/nbody/nbody -benchmark -numbodies=512000 -cpu"
```

> This is a longer test. You should see GPU utilization spike in `nvidia-smi`
> while it is running (run `watch -n 1 nvidia-smi` in a second terminal).

---

## Summary Table

| Component           | Check Command                              | Expected Result                                      |
|---------------------|--------------------------------------------|------------------------------------------------------|
| Ubuntu 24.04        | `lsb_release -a`                           | Ubuntu 24.04 LTS                                     |
| Kernel HWE          | `uname -r`                                 | `6.17.x-1021-nvidia`                                 |
| Architecture        | `uname -m`                                 | `aarch64`                                            |
| NVIDIA driver       | `nvidia-smi`                               | Driver 580.x, Persistence On, Memory: Not Supported  |
| DCGM service        | `systemctl is-active nvidia-dcgm`          | `active`                                             |
| CUDA toolkit        | `nvcc --version`                           | CUDA release 13.x                                   |
| NCCL                | `dpkg -l libnccl2`                         | 2.28.9-1+cuda13.0                                    |
| Docker              | `docker version`                           | Client + Server versions                             |
| NVIDIA Container TK | `nvidia-ctk --version`                     | Version string                                       |
| GPU in container    | `docker run --gpus=all ... nvidia-smi`     | Same GPU output as host (Memory: Not Supported OK)   |
| System memory       | `grep MemTotal /proc/meminfo`              | ~131072 MB (128 GB)                                  |
| ConnectX-7          | `rdma link show`                           | mlx5_0/1 state ACTIVE                               |
| 10GbE (Realtek)     | `ip -br addr show enP7s7`                  | UP with IP address                                   |
| Secure Boot         | `mokutil --sb-state`                       | SecureBoot enabled                                   |

## Next Step

See [06-optimizations.md](06-optimizations.md) for optional post-install tuning
(CPU governor, nvsm removal, Wi-Fi disable, swap tuning).
