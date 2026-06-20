# 06 - Post-Install Optimizations

Optional but recommended tuning for a dedicated GPU/AI inference server.

## Power Draw - What to Expect

The idle power floor for a GB10 system with ConnectX-7 networking is **~40-45 W** at the wall.
This is a hardware reality, not a software problem:

| Component | Est. idle draw |
|---|---|
| GB10 SoC (CPU + GPU baseline) | ~15-18 W |
| ConnectX-7 high-speed networking | ~16-20 W |
| NVMe SSD | ~3-5 W |
| Board VRMs, fans | ~3-5 W |

The ConnectX-7 NIC is a PCIe device drawing power at the silicon level regardless
of software state. The optimizations below reduce CPU overhead and improve system
cleanliness but will not meaningfully move the watt meter.

> **Why can't software reduce NIC power?**
> ConnectX-7 at PCIe Gen5 speeds does not support ASPM (`LnkCap: ASPM not supported`).
> The mlx5 driver holds an active power reference even on link-down ports, preventing
> D3 entry. There is no practical software-only path to reduce this idle draw.

---

## Disable Wi-Fi (hardwired machines)

The GB10 includes a MediaTek Wi-Fi adapter (`wlP9s9`). On a hardwired server
it serves no purpose and can be persistently disabled via a udev rule:

```bash
echo 'SUBSYSTEM=="net", ACTION=="add", KERNEL=="wlP9s9", RUN+="/sbin/ip link set %k down"' | \
  sudo tee /etc/udev/rules.d/99-disable-wifi.rules
sudo ip link set wlP9s9 down
```

Takes effect immediately and persists across reboots without any additional packages.

---

## Remove nvsm (DGX Fleet Management)

The NVIDIA repos pull in `nvsm`, a DGX datacenter management stack (Redfish REST
API, MQTT broker, health notifier daemon). It is designed for managed DGX fleets
and is not needed on a standalone Ubuntu server. On a non-DGX system, `nvsm-core`
and `nvsm-api-gateway` crash-loop continuously, and `notifier_nvsm` spins in a
Python loop consuming ~14% CPU at idle.

```bash
sudo apt-get purge -y nvsm
sudo systemctl reset-failed
```

Verify it is gone:

```bash
systemctl list-units --all | grep -i nvsm
# Should return nothing
```

---

## CPU Frequency Governor

The GB10 Grace CPU has two core clusters:

| Cluster | Cores | Max Frequency |
|---|---|---|
| Efficiency (E-cores) | 10 | 2808 MHz |
| Performance (P-cores) | 10 | 3900 MHz |

Dynamic scaling works well - cores drop to ~338 MHz at idle and ramp to max within
milliseconds under load. Choose the governor that fits your workload:

### performance (default - matches DGX OS)

Clocks always at maximum. Best for inference workloads where latency matters.
This is the DGX OS default and what this guide uses.

```bash
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Persist across reboots
sudo apt-get install -y cpufrequtils
echo 'GOVERNOR=performance' | sudo tee /etc/default/cpufrequtils
```

### schedutil (optional - dynamic scaling)

Lower idle power. Slight frequency ramp latency on the first request after
an idle period (~milliseconds).

```bash
echo schedutil | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Persist across reboots
sudo apt-get install -y cpufrequtils
echo 'GOVERNOR=schedutil' | sudo tee /etc/default/cpufrequtils
```

Verify the active governor:

```bash
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Check current frequencies across all cores
paste /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq | tr '\t' '\n' | sort | uniq -c
```

---

## Disable Automatic Updates

Surprise kernel or driver updates will cause GPU module reloads and service
disruptions mid-session. If not already done:

```bash
sudo apt-get purge -y unattended-upgrades
sudo systemctl disable --now apt-daily.timer apt-daily-upgrade.timer
```

---

## Swap Configuration

The GB10 has 128 GB of unified memory. The default 8 GB swap created by the
Ubuntu installer is sufficient as overflow protection, but you may want to
tune `vm.swappiness` to prevent the kernel from swapping eagerly:

```bash
# Check current swappiness (default 60)
cat /proc/sys/vm/swappiness

# Set to 10 - only swap under real memory pressure
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-gb10.conf
sudo sysctl -p /etc/sysctl.d/99-gb10.conf
```

---

## Page Cache Flush (before large model loads)

On UMA systems, the GPU and CPU share the same memory pool. If a CUDA workload
fails with out-of-memory errors despite seemingly having free memory, the page
cache may be holding onto reclaimable pages. Flush it first:

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

This is safe to run at any time. It does not affect running processes.
