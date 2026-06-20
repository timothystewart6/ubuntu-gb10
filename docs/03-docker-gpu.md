# 03 - Docker CE + NVIDIA Container Toolkit

## Overview

Containers are the standard way to run GPU-accelerated workloads (CUDA, PyTorch,
TensorFlow, etc.) on NVIDIA hardware. This guide installs Docker CE and the NVIDIA
Container Toolkit, which allows containers to access the host GPUs.

Reference: <https://docs.nvidia.com/dgx/dgx-os-7-user-guide/installing_on_ubuntu.html#installing-docker-and-the-nvidia-container-toolkit>

---

## Prerequisites

- NVIDIA GPU driver installed and verified (`nvidia-smi` works) - see [02-nvidia-stack.md](02-nvidia-stack.md)
- Ubuntu Server 24.04 with NVIDIA repos already configured

---

## Check if Already Installed

If you installed `nvidia-system-extra` in the previous step, Docker CE and the
NVIDIA Container Toolkit may already be installed:

```bash
docker --version
nvidia-ctk --version
```

If both return version strings, skip to [Step 3 - Enroll MOK key](#step-3---enroll-dkms-signing-key-secure-boot) below.

---

## Step 1 - Install Docker CE

If Docker is not yet installed:

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

> **Important:** Do NOT install Docker as a snap package (`snap install docker`).
> This will conflict with the `nvidia-container-toolkit` package.

Enable and start Docker:

```bash
sudo systemctl enable --now docker
```

Add your user to the docker group (so you can run docker without sudo):

```bash
sudo usermod -aG docker $USER
# Log out and back in for this to take effect, or use:
newgrp docker
```

Verify Docker is running:

```bash
docker version
docker run --rm hello-world
```

---

## Step 2 - Install NVIDIA Container Toolkit

```bash
sudo apt install -y nvidia-container-toolkit nv-docker-options
```

---

## Step 3 - Enroll DKMS Signing Key (Secure Boot)

If Secure Boot is enabled, the NVIDIA kernel modules (built by DKMS during driver
install) must be signed with a key that is enrolled in the UEFI MOK database.
Without this step, `modprobe nvidia` will fail with **"Key was rejected by service"**.

Check if the key is already enrolled:

```bash
sudo mokutil --test-key /var/lib/shim-signed/mok/MOK.der
# Output: "... is already enrolled" = nothing to do, skip this step
# Output: "... is not enrolled"   = follow steps below
```

If not enrolled, queue the key for enrollment:

```bash
sudo mokutil --import /var/lib/shim-signed/mok/MOK.der
# Enter a memorable one-time password when prompted
# You will need this password once at the next boot
```

Reboot:

```bash
sudo reboot
```

At the **blue "Perform MOK management" screen** that appears before GRUB:

1. Select **Enroll MOK**
2. Select **Continue**
3. Enter the password you set above
4. Select **Yes**
5. Select **Reboot**

> **Note:** This screen has a ~10 second timeout. Watch the console (KVM/iDRAC/iLO)
> immediately after POST. If you miss it, the enrollment stays queued - just reboot
> and watch again.

After reboot, verify the driver loads:

```bash
nvidia-smi
# Should show the GB10 GPU - if you still get "Driver Not Loaded", check:
# sudo mokutil --test-key /var/lib/shim-signed/mok/MOK.der
```

---

## Step 4 - Configure the NVIDIA Container Runtime

Tell Docker to use the NVIDIA container runtime:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
```

Restart Docker to apply the config:

```bash
sudo systemctl restart docker
```

Verify the runtime config was written:

```bash
cat /etc/docker/daemon.json
```

Expected output includes:

```json
{
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    }
}
```

---

## Step 5 - Verify GPU Access in Containers

Run a test container that invokes `nvidia-smi` inside the container:

```bash
docker run --gpus=all --rm nvcr.io/nvidia/cuda:12.6.2-base-ubuntu24.04 nvidia-smi
```

> This will download the CUDA base container from NVIDIA NGC (requires internet
> access). The first run will be slower while the image layers download.

Expected output: same as running `nvidia-smi` on the host - shows all GPUs with
Persistence-Mode On.

### Quick local GPU test (no download required)

```bash
docker run --gpus=all --rm ubuntu:24.04 bash -c "ls /dev/nvidia*"
```

Expected output: `/dev/nvidia0`, `/dev/nvidiactl`, `/dev/nvidia-uvm`, etc.

---

## Step 6 - (Optional) Configure Default Docker Runtime

To make `nvidia` the default runtime so you do not need `--gpus=all` on every
`docker run`, edit `/etc/docker/daemon.json`:

```bash
sudo tee /etc/docker/daemon.json > /dev/null <<'DOCKERCONF'
{
    "default-runtime": "nvidia",
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    }
}
DOCKERCONF
```

> **Note:** Setting nvidia as the default runtime means ALL containers run with
> GPU access by default. Only do this if this host is dedicated to GPU workloads.

Restart Docker:

```bash
sudo systemctl restart docker
```

---

## Next Step

Continue to [04-doca-ofed.md](04-doca-ofed.md) for ConnectX-7 DOCA-OFED drivers
(optional, skip if you don't need RDMA/InfiniBand), then [05-verify.md](05-verify.md)
for the full post-install verification checklist.
