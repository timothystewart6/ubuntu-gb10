# 01 - Ubuntu Server 24.04 Installation

## Overview

This guide covers installing Ubuntu Server 24.04 LTS on the ASUS Ascent GX10.
The GX10 uses the **NVIDIA GB10 Grace Blackwell Superchip** - an **ARM64** system
identical in software configuration to the NVIDIA DGX Spark. We use the standard
Ubuntu Server **arm64** ISO (not the DGX ISO) with the minimal package set.

> **Architecture note:** This system is ARM64, not x86_64. Make sure to download
> the arm64 ISO and use arm64 packages throughout.

---

## Prerequisites

- USB flash drive, 8 GB or larger
- Ubuntu Server 24.04 LTS **arm64** ISO downloaded from <https://ubuntu.com/download/server/arm>
- Access to the machine's console (keyboard + monitor via HDMI 2.1b port, or USB-C DisplayPort)

---

## Step 1 - Download and Write the ISO

### Download

```bash
# On your local machine - download the ARM64 ISO
# Current release is 24.04.4 (Noble Numbat)
wget https://cdimage.ubuntu.com/releases/24.04/release/ubuntu-24.04.4-live-server-arm64.iso
```

Verify the checksum:

```bash
# Download the SHA256 checksum file
wget https://cdimage.ubuntu.com/releases/24.04/release/SHA256SUMS

# Verify
sha256sum -c SHA256SUMS --ignore-missing
```

Expected output contains: `ubuntu-24.04.4-live-server-arm64.iso: OK`

### Write to USB

**macOS:**

```bash
# Find the USB device - look for /dev/diskN matching your USB size
diskutil list

# Unmount the disk (replace N with your disk number)
diskutil unmountDisk /dev/diskN

# Write the ISO (replace N with your disk number - use rdiskN for speed)
sudo dd if=ubuntu-24.04.4-live-server-arm64.iso of=/dev/rdiskN bs=4m status=progress

# Eject when done
diskutil eject /dev/diskN
```

**Linux:**

```bash
# Find the USB device
lsblk

# Write the ISO (replace sdX with your device, e.g. sdb - NOT a partition like sdb1)
sudo dd if=ubuntu-24.04.4-live-server-arm64.iso of=/dev/sdX bs=4M status=progress conv=fsync
```

---

## Step 2 - Boot from USB

1. Insert the USB drive into the ASUS GX10.
2. Power on. The GX10 boots via UEFI on ARM64 - access the boot menu during POST
   (typically hold or tap the appropriate key; consult ASUS GX10 documentation for
   the exact key, or use the UEFI boot manager from within the firmware setup).
3. Select the USB drive as the boot device.
4. At the GRUB menu, select **"Ubuntu Server with the HWE kernel"** - NOT the default
   entry. The standard kernel fails to find the live filesystem on the GX10's USB
   controller. The HWE kernel boots successfully.

> **If you see "Unable to find a medium containing a live file system":** You booted
> the wrong GRUB entry. Reboot and select the HWE kernel. If the HWE kernel also
> fails, press `e` at the GRUB menu on the HWE entry, find the `linux` line, append
> `rootdelay=30` to the end, then press Ctrl+X to boot.

---

## Step 3 - Ubuntu Installer Walkthrough

### Language and Keyboard

- Select **English** (or your preferred language).
- Select your keyboard layout.

### Installer Update

- If prompted to update the installer, select **Update to the new installer** (recommended) or **Continue without updating**.

### Installation Type - Choose Minimized

When the installer asks which base to install, select **"Ubuntu Server (minimized)"**
rather than the default "Ubuntu Server".

The minimized variant strips out manuals, locales, optional CLI utilities, and
non-essential services. It is still fully bare-metal installable and supports
everything we need. This is the right choice for a dedicated GPU/AI server.

> **Why not Ubuntu minimal cloud images?** The cloud images at
> cloud-images.ubuntu.com are pre-installed disk images built for hypervisors
> (AWS, GCP, OpenStack). Using them on bare metal requires manual cloud-init
> `NoCloud` datasource setup and UEFI bootloader work. The memory savings vs.
> "Ubuntu Server (minimized)" are ~50 MB - not worth the complexity on a
> 128 GB unified memory system.

### Network Configuration

- The installer will attempt DHCP on all interfaces automatically. Continue without changes.
- Configure a DHCP reservation on your router/DHCP server using the machine's MAC address if you want a stable IP.

> **GX10 networking note:** The ASUS GX10 includes NVIDIA ConnectX-7 high-speed
> networking plus a separate Realtek 10GbE controller. A MediaTek Wi-Fi adapter
> (`wlP9s9`) is also present and works as a fallback. The installer may detect a
> different interface name than what is active after reboot - see Step 4 for how
> to fix this.

### Storage Configuration

For a single-disk or simple setup:

- Select **"Use an entire disk"**.
- Select the target drive (the OS/boot drive - typically a smaller SSD, NOT the GPU NVMe data drives).
- Leave **"Set up this disk as an LVM group"** unchecked for simplicity (LVM adds flexibility but complexity).
- Review the partition summary and select **Done**, then **Continue**.

> **Note:** If you have separate OS and data drives, only select the OS drive here.
> Data drives can be configured after install.

### Profile Setup

- Your name: choose anything (e.g. `admin`)
- Server name: `gb10-1`
- Username: choose anything (e.g. `admin`)
- Password: set a strong password

### Ubuntu Pro

- Select **Skip for now** unless you have an Ubuntu Pro token.

### SSH Setup

- Select **"Install OpenSSH server"** - this is required for remote management.
- You can import your SSH key from GitHub/Launchpad here, or add it manually after install.

### Featured Server Snaps

- **Do NOT install Docker as a snap.** Docker CE will be installed via apt later.
- Leave all snaps unselected and press **Done**.

### Installation

- Wait for the installation to complete. This typically takes 5-15 minutes depending on hardware.
- Select **"Reboot Now"** when prompted.
- Remove the USB drive when prompted and press Enter.

---

## Step 4 - First Boot and Initial Access

After reboot, log in with the username and password created during installation.

### Fix network interface name (likely needed)

The installer frequently detects a different interface name in the live environment
than the one present in the installed system. Check and fix the netplan config:

```bash
sudo cat /etc/netplan/*.yaml
```

If the interface name in the file (e.g. `enP7s7`) does not appear in `ip a`, fix it:

```bash
# Find your actual interface names
ip a

# Replace the wrong name with the correct one (e.g. enp1s0f0np0)
sudo sed -i 's/enP7s7/enp1s0f0np0/' /etc/netplan/50-cloud-init.yaml
sudo netplan apply
```

If no ethernet interface gets a DHCP lease (e.g. the cable goes to another GX10,
not a router), configure Wi-Fi as a temporary fallback:

```bash
sudo tee /etc/netplan/50-cloud-init.yaml > /dev/null << 'EOF'
network:
  version: 2
  ethernets:
    enp1s0f0np0:
      dhcp4: true
  wifis:
    wlP9s9:
      dhcp4: true
      access-points:
        "YOUR_SSID":
          password: "YOUR_PASSWORD"
EOF
sudo netplan apply
```

### Verify the system came up cleanly

```bash
# Check kernel version and architecture
uname -r && uname -m
```

Expected output (HWE kernel, ARM64):

```terminal
6.17.0-35-generic
aarch64
```

```bash
# Full system identity
hostnamectl
```

Expected output on GX10:

```terminal
 Static hostname: gb10-1
       Icon name: computer-server
         Chassis: server
      Machine ID: <unique>
         Boot ID: <unique>
Operating System: Ubuntu 24.04.4 LTS
          Kernel: Linux 6.17.0-35-generic
    Architecture: arm64
 Hardware Vendor: ASUSTeK COMPUTER INC.
  Hardware Model: GX10
Firmware Version: GX10DGX.0104.2026.0326.1657
```

```bash
# Check network connectivity
ping -c 3 8.8.8.8
```

### Update all packages and remove unattended upgrades

Run these together - they are safe to chain:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt dist-upgrade -y
sudo apt purge -y unattended-upgrades
```

`dist-upgrade` handles kernel transitions and dependency changes that plain
`upgrade` skips. Purging `unattended-upgrades` prevents surprise kernel or
driver updates mid-session.

### Grant passwordless sudo (recommended for automation)

Required if you intend to run commands remotely without a TTY:

```bash
echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/$USER
```

### Set the hostname

```bash
sudo hostnamectl set-hostname gb10-1
# Verify
hostnamectl
```

---

## Step 5 - Deploy SSH Key

From your local machine:

```bash
ssh-copy-id <user>@gb10-1.local
```

Test that key-based login works:

```bash
ssh <user>@gb10-1.local
```

---

## Step 6 - Critical Stability Fix: Load the SBSA Watchdog Driver

> **Apply this immediately after install.** Without it, GB10 / DGX Spark systems
> hard-reset roughly every 20 minutes - even when completely idle with no GPU or
> Docker workload running. This is a fix, not an optional tweak.

### Symptom

The machine reboots on a near-exact ~20-minute interval. The kernel log goes
silent and `pstore` is empty (no panic, Xid, MCE, or soft-lockup) - the box just
resets. Boot-to-boot intervals are metronome-precise (e.g. 20m38s, 20m40s,
20m41s), which is the signature of a hardware watchdog, not a random fault.

### Cause

The GB10/GX10 firmware arms the **ARM SBSA Generic Watchdog** at boot (a 2-stage
timer, ~10 min per stage = ~20 min to reset) and expects the OS to take ownership
of it. Stock Ubuntu does **not** load the `sbsa_gwdt` driver by default, so the
watchdog is never serviced and fires on schedule.

Confirm the watchdog exists but has no driver bound:

```bash
# Firmware advertises the watchdog...
sudo dmesg | grep -i 'SBSA generic Watchdog'
# -> ACPI GTDT: found 1 SBSA generic Watchdog(s).

# ...and the platform device is present...
ls /sys/bus/platform/devices/ | grep sbsa-gwdt
# -> sbsa-gwdt.0

# ...but no driver is loaded and there is no /dev/watchdog:
lsmod | grep sbsa_gwdt        # (empty)
ls /dev/watchdog*             # No such file or directory
```

### Fix

Load the driver so the kernel adopts the running watchdog and keeps it alive
while the system is healthy. A genuine kernel freeze stops the keepalive and the
watchdog resets the box within ~10 s, so real-hang recovery is retained.

```bash
# Load it now
sudo modprobe sbsa_gwdt

# Persist across reboots
echo sbsa_gwdt | sudo tee /etc/modules-load.d/sbsa_gwdt.conf
```

Verify it is active:

```bash
sudo dmesg | grep -i sbsa-gwdt
# -> sbsa-gwdt sbsa-gwdt.0: Initialized with 10s timeout @ 1000000000 Hz, action=0. [enabled]

cat /sys/class/watchdog/watchdog0/identity   # -> SBSA Generic Watchdog
cat /sys/class/watchdog/watchdog0/timeout    # -> 10
```

The box should now run indefinitely past the 20-minute mark.

> **Proper vendor fix (secondary):** The SOC firmware is what arms the watchdog.
> The latest ASUS/NVIDIA platform firmware (e.g. ASUS GX10 BIOS bundle v0104,
> SOC FW 3.0.6 / EC 2.78.18.3 / PD 5.7) may correct the watchdog handoff and is
> worth applying - see [06-optimizations.md](06-optimizations.md#firmware-updates-fwupd).
> Flash carefully: keep the unit on AC, do not run headless during the flash, and
> do one machine at a time. The driver fix above is what makes the system usable
> in the meantime and is harmless to keep even after a firmware update.

---

## Step 7 - Critical Fix: Set nvidia-container-runtime to Legacy Mode

### Symptom

Any `docker run --gpus all <nvidia-cuda-image>` fails immediately at container
start with:

```
exec /opt/nvidia/nvidia_entrypoint.sh: exec format error
```

GPU hardware is healthy - `nvidia-smi` on the host works fine.

### Cause

`/opt/nvidia/nvidia_entrypoint.sh` is shipped as a 0-byte placeholder in NVIDIA
CUDA base images. The `nvidia-container-runtime` is supposed to populate it via
its **legacy mode** hook at container startup. With `nvidia-container-toolkit`
1.19+, the default mode is `"auto"`. When CDI device specs are present under
`/etc/cdi` (which the toolkit generates automatically), `auto` selects **CDI
mode** instead of legacy mode. CDI mode does not run the hook, so the entrypoint
stays 0 bytes and the kernel returns `ENOEXEC` when Docker tries to exec it.

Confirm the current (broken) state:

```bash
grep "^mode" /etc/nvidia-container-runtime/config.toml
# mode = "auto"   <- wrong

docker info | grep cdi
# cdi: nvidia.com/gpu=0   <- CDI active
```

### Fix

Force legacy mode so the hook always runs:

```bash
sudo sed -i 's/^mode = .*/mode = "legacy"/' /etc/nvidia-container-runtime/config.toml
sudo systemctl restart docker
```

Verify:

```bash
docker run --rm --gpus all --entrypoint nvidia-smi \
  nvidia/cuda:13.2.0-devel-ubuntu24.04
# Should print the GPU table, no exec format error
```

The Ansible `nvidia_stack` role handles this automatically (see
`playbooks/roles/nvidia_stack/tasks/main.yml`). Run it to apply idempotently:

```bash
ansible-playbook -i inventory/hosts.yml site.yml --tags nvidia_stack
```

---

## Next Step

Continue to [02-nvidia-stack.md](02-nvidia-stack.md) to install the NVIDIA software stack.
