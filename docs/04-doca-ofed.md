# 04 - ConnectX-7 and DOCA-OFED

## Overview

The ASUS Ascent GX10 includes an **NVIDIA ConnectX-7 NIC** built into the system.
This enables:

- Ultra-fast data transfer between two linked GX10 units (for 200B+ parameter models)
- High-speed RDMA and GPUDirect RDMA for distributed AI workloads
- IEEE 1588v2 PTP for microsecond time synchronization

The NVIDIA DOCA-OFED software provides the kernel drivers, user-space libraries,
and management tools for ConnectX NICs (successor to MLNX_OFED).

Reference: <https://docs.nvidia.com/dgx/dgx-os-7-user-guide/installing_on_ubuntu.html#installing-the-doca-ofed-package>

---

## Prerequisites

- NVIDIA repos already configured (see [02-nvidia-stack.md](02-nvidia-stack.md))
- `sudo` access

---

## Step 1 - Check if ConnectX-7 is Detected

```bash
# List network interfaces
ip link show

# Check for Mellanox/NVIDIA NIC in PCI devices
lspci | grep -i mellanox
lspci | grep -i connectx
```

The ConnectX-7 NIC should appear. If nothing shows, check that the NIC
is enabled in UEFI settings.

---

## Step 2 - Install DOCA-OFED

### 2a - Install the DOCA repo package and NVIDIA repo keys

```bash
sudo apt update
sudo apt install -y doca-bos8-latest-repo nvidia-repo-keys
```

> If you hit a GPG error after `sudo apt update`, run:
>
> ```bash
> sudo apt-key adv --fetch-keys https://repo.download.nvidia.com/baseos/ubuntu/noble/arm64/nvidia-repo-keys.gpg
> ```

### 2b - Update package list with DOCA repository

```bash
sudo apt update
```

### 2c - Full upgrade to resolve new dependencies

```bash
sudo apt full-upgrade -y
```

### 2d - Install MLNX/ConnectX drivers

```bash
sudo apt install -y nvidia-system-mlnx-drivers
```

---

## Step 3 - Verify ConnectX-7 Driver

```bash
# Check that the mlx5_core driver is loaded
lsmod | grep mlx5

# Show NIC firmware and driver version
sudo mst status
sudo mlxconfig -d /dev/mst/mt4129_pciconf0 query 2>/dev/null || \
  sudo flint -d /dev/mst/mt4129_pciconf0 query 2>/dev/null

# List RDMA devices
rdma link show
ibstat 2>/dev/null || echo "ibstat not available (may not need InfiniBand)"
```

---

## Step 4 - Verify Network Connectivity

```bash
# List all interfaces including the ConnectX-7
ip link show

# Check if the ConnectX-7 interface got an IP (often via DHCP on first boot)
ip addr show
```

The ConnectX-7 port will appear as an interface named something like `enp1s0f0`
or `mlx5_0`. Configure it via netplan as needed for your network.

---

## Linking Two GX10 Units

Two ASUS Ascent GX10 systems can be directly connected via their ConnectX-7 ports
using a 400G or compatible cable (direct attach copper or AOC). This allows running
models up to 405B parameters (e.g., Llama 3.1 405B) across both units.

For three or more units, a network switch supporting the ConnectX-7 link speed
is required.

Configuration of multi-GX10 clustering is outside the scope of this guide.
Refer to the [DGX Spark Stacking documentation](https://docs.nvidia.com/dgx/dgx-spark/spark-clustering.html).

---

## 10GbE RJ45 Port (Realtek RTL8127)

The GX10 has a **1x 10GbE copper RJ45 port** driven by a **Realtek RTL8127** chip,
separate from the ConnectX-7 high-speed networking. On a working unit (gb10-1 running DGX OS),
this chip appears at PCI address `0007:01:00.0` and is managed by the proprietary
`r8127` driver.

The `r8127` kernel module IS included in the `linux-image-6.17.0-1021-nvidia`
package, so it is available on Ubuntu installs with the nvidia kernel.

### Checking for the chip

```bash
# The Realtek sits behind an NVIDIA PCIe bridge at domain 0007
sudo lspci -D | grep '0007:'

# On a working unit you will see:
#   0007:00:00.0 PCI bridge: NVIDIA Corporation Device 22d0 (rev 01)
#   0007:01:00.0 Ethernet controller: Realtek Semiconductor Co., Ltd. Device 8127 (rev 05)

# Load the driver
sudo modprobe r8127

# Confirm the interface appeared
ip link show | grep enP7
```

### Chip absent after fresh Ubuntu install - root cause and fix

After wiping a GX10 from DGX OS to Ubuntu, the Realtek chip may **disappear from
the PCIe bus** despite the NVIDIA PCIe bridge being present:

```bash
$ sudo lspci -D | grep '0007:'
0007:00:00.0 PCI bridge: NVIDIA Corporation Device 22d0 (rev 01)
# 0007:01:00.0 missing - Realtek chip not enumerated
```

This is **not a hardware defect**. The root cause is a combination of two issues:

**1. Fast Boot disables PCIe NIC Option ROM execution**

The BIOS "Fast Boot" setting (Boot tab) boots with a minimal set of devices and
skips executing PCIe NIC Option ROMs. Without the Realtek Option ROM running at
POST, the chip's PCIe Data Link Layer never fully initializes and the chip is
invisible to the OS. Fix: disable Fast Boot in BIOS.

**2. Missing Realtek PXE UEFI boot entry**

The Ubuntu installer deletes all non-Ubuntu UEFI boot entries, including the
`UEFI: PXE IPv4 Realtek PCIe 10 GBE Family Controller` entry that the BIOS uses
to signal that it should initialize the Realtek NIC during POST. Without this
entry, the BIOS does not execute the chip's Option ROM even with Fast Boot
disabled, leaving the chip's DL layer incomplete and the device unreachable.

The chip's PCIe physical layer does partially train (bridge shows `LnkSta: Speed
2.5GT/s, Width x1`), but the Data Link Layer stays inactive (`DLActive-`) and
config space reads return nothing.

#### Fix procedure

**Step 1 - Disable Fast Boot in BIOS**

Enter BIOS (Boot tab), set `Fast Boot` to `[Disabled]`, Save & Exit. Fast Boot
must be disabled before the chip will initialize properly.

**Step 2 - Cold boot (AC power cycle)**

A warm reboot is not sufficient. The chip requires a genuine cold start:

1. `sudo shutdown -h now`
2. Remove AC power from the machine (flip PDU switch or unplug)
3. Wait 30 seconds for PCIe capacitors to discharge
4. Restore AC power and power on

After the cold boot, `0007:01:00.0` will appear in `lspci` and the `r8127`
driver will bind automatically.

**Step 3 - Write the correct UEFI boot entry**

With Secure Boot temporarily disabled (BIOS Security tab), write the Realtek PXE
entry with the chip's real MAC address:

```bash
# Get the Realtek MAC address
RTL_MAC=$(cat /sys/class/net/enP7s7/address)
echo "Realtek MAC: $RTL_MAC"

# Delete the dummy entry if present, then write the correct one
# (requires Secure Boot disabled - kernel lockdown blocks efivarfs writes
#  for custom device paths when Secure Boot is active)
sudo efibootmgr -b 0001 -B 2>/dev/null || true
```

Then save the following Python script to a temp file and run it as root
(replace `mac_bytes` with the 6 MAC bytes from `enP7s7`):

```bash
# First get your MAC bytes
cat /sys/class/net/enP7s7/address
# e.g. aa:bb:cc:dd:ee:ff -> bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])

# Save the script, edit mac_bytes, then run it
sudo nano /tmp/write_rtl_boot.py
sudo python3 /tmp/write_rtl_boot.py
```

```python
#!/usr/bin/env python3
import os, struct, subprocess

BOOT_GUID = "8be4df61-93ca-11d2-aa0d-00e098032b8c"
VARPATH = f"/sys/firmware/efi/efivars/Boot0001-{BOOT_GUID}"

desc = "UEFI: PXE IPv4 Realtek PCIe 10 GBE Family Controller"
desc_ucs2 = (desc + "\x00").encode("utf-16-le")

# Update mac_bytes with the actual MAC from: cat /sys/class/net/enP7s7/address
mac_bytes = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])  # replace with your unit's MAC

acpi_node = bytes([0x02,0x01,0x0C,0x00,0xD0,0x41,0x08,0x0A,0x07,0x00,0x00,0x00])
pci_node  = bytes([0x01,0x01,0x06,0x00,0x00,0x00])
mac_node  = bytes([0x03,0x0B,0x25,0x00]) + mac_bytes + bytes(27)
ipv4_node = bytes([0x03,0x0C,0x1B,0x00]) + bytes(23)
end_node  = bytes([0x7F,0xFF,0x04,0x00])
device_path = acpi_node + pci_node + pci_node + mac_node + ipv4_node + end_node

load_option = struct.pack("<I", 1) + struct.pack("<H", len(device_path)) + desc_ucs2 + device_path
full_data = struct.pack("<I", 7) + load_option  # NV+BS+RT attributes

subprocess.run(["chattr", "-i", VARPATH], capture_output=True)
# Create entry first if it doesn't exist
if not os.path.exists(VARPATH):
    subprocess.run(["efibootmgr", "--create", "--disk", "/dev/nvme0n1",
                    "--part", "1", "--label", "UEFI: PXE IPv4 Realtek PCIe 10 GBE Family Controller",
                    "--loader", "\\EFI\\ubuntu\\shimaa64.efi"], capture_output=True)

fd = os.open(VARPATH, os.O_WRONLY)
os.write(fd, full_data)
os.close(fd)
print("Boot0001 written")
subprocess.run(["efibootmgr", "-o", "0000,0001"])  # Ubuntu first, Realtek second
```

**Step 4 - Re-enable Secure Boot**

Return to BIOS Security tab, re-enable Secure Boot, Save & Exit. The chip will
initialize on every subsequent boot because the BIOS now has the PXE entry and
will execute the Realtek Option ROM during POST.

#### Why the BIOS needs the PXE entry

The Realtek RTL8127 requires its UEFI Option ROM (stored on the chip itself) to
run during POST to complete PCIe Gen4 equalization and bring up the Data Link
Layer. The BIOS only executes a NIC's Option ROM when a corresponding boot entry
exists for that NIC. On gb10-1 (DGX OS), the entry was created during the initial
DGX OS install and was never deleted. On gb10-1 (reimaged to Ubuntu), the Ubuntu
installer removed it. One AC power cycle after the BIOS entry is restored is
sufficient to bring the chip to full Gen4 operation (`16GT/s, DLActive+`).

#### netplan configuration

Once the chip is present, configure the interface:

```bash
sudo tee /etc/netplan/60-rtl8127.yaml << 'EOF'
network:
  version: 2
  ethernets:
    enP7s7:
      dhcp4: true
      match:
        macaddress: aa:bb:cc:dd:ee:ff   # replace with your unit's MAC (from: ip link show enP7s7)
      set-name: enP7s7
EOF
sudo chmod 600 /etc/netplan/60-rtl8127.yaml
sudo netplan apply
```

Verify:

```bash
ip -br addr show enP7s7
sudo ethtool enP7s7 | grep Speed
# Expected: Speed: 10000Mb/s
```

---

## Next Step

Continue to [05-verify.md](05-verify.md) for the full post-install verification
checklist.
