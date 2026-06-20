# 07 - Dual-Node Setup (Two GB10 Systems)

## Overview

Two GB10 systems can be connected directly via a QSFP cable across their
NVIDIA ConnectX-7 NICs, establishing a **200 Gbps** direct link for multi-node
distributed workloads (inference, fine-tuning, NCCL collectives).

This guide covers network configuration, SSH setup, and NCCL validation.

References:

- <https://build.nvidia.com/spark/connect-two-sparks/stacked-sparks>
- <https://build.nvidia.com/spark/nccl/stacked-sparks>

---

## Prerequisites

- Two GB10 systems, each with the full NVIDIA stack installed (docs 01-06)
- One QSFP cable (100G or 200G) for the direct inter-node link
- Both systems reachable via your management network (Realtek 10GbE)
- DOCA-OFED installed on both nodes - see [04-doca-ofed.md](04-doca-ofed.md)
- Same username on both systems (this guide uses `automation`)

---

## Step 1 - Physical Connection

Connect the QSFP cable between any CX-7 port on each system. The ConnectX-7
NIC on each GB10 has two physical ports exposed as:

| Interface     | Description                    |
|---------------|--------------------------------|
| `enp1s0f0np0` | CX-7 physical port 0           |
| `enp1s0f1np1` | CX-7 physical port 1           |

> **Note:** Each physical port also has an alternative name prefixed with
> `enP2p1s0f*`. NVIDIA recommends using only the `enp1s0f*` names.

After connecting the cable, confirm the link comes up:

```bash
ibdev2netdev
```

Expected output (one port will show `Up`):

```terminal
rocep1s0f0 port 1 ==> enp1s0f0np0 (Down)
rocep1s0f1 port 1 ==> enp1s0f1np1 (Up)
roceP2p1s0f0 port 1 ==> enP2p1s0f0np0 (Down)
roceP2p1s0f1 port 1 ==> enP2p1s0f1np1 (Up)
```

> If no interface shows `Up`, check the cable, reboot both systems, and retry.

---

## Step 2 - Configure CX-7 Network Interfaces

Run the following on **both nodes**. This configures both CX-7 ports with
automatic link-local IPv4 addresses (`169.254.x.x`).

> This option works with a **single QSFP cable**. For two cables (full
> bandwidth across all four interfaces), use manual IP assignment - see the
> NVIDIA Connect Two Sparks guide for Option 2.

```bash
sudo tee /etc/netplan/40-cx7.yaml > /dev/null <<'EOF'
network:
  version: 2
  ethernets:
    enp1s0f0np0:
      link-local: [ ipv4 ]
    enp1s0f1np1:
      link-local: [ ipv4 ]
EOF
sudo chmod 600 /etc/netplan/40-cx7.yaml
sudo netplan apply
```

Verify the link-local addresses were assigned:

```bash
ip -4 addr show enp1s0f0np0
ip -4 addr show enp1s0f1np1
```

Note the `169.254.x.x` addresses - you will need them for the NCCL test.

---

## Step 3 - SSH Between Nodes

NCCL multi-node tests use `mpirun` which requires passwordless SSH between
nodes on the inter-connect interface.

### Generate a keypair (if not already present)

Run on **both nodes**:

```bash
test -f ~/.ssh/id_ed25519 || ssh-keygen -t ed25519 -N '' -f ~/.ssh/id_ed25519
```

### Exchange public keys

From **node 1**, copy its key to node 2 and vice versa:

```bash
# From node 1 - copy node 1's key to node 2 (replace IP with node 2's link-local IP)
ssh-copy-id -i ~/.ssh/id_ed25519.pub automation@<node2-cx7-ip>

# From node 2 - copy node 2's key to node 1
ssh-copy-id -i ~/.ssh/id_ed25519.pub automation@<node1-cx7-ip>
```

### Verify

```bash
# From node 1 - should print node 2's hostname without a password prompt
ssh -o StrictHostKeyChecking=no automation@<node2-cx7-ip> hostname

# From node 2
ssh -o StrictHostKeyChecking=no automation@<node1-cx7-ip> hostname
```

---

## Step 4 - Build NCCL from Source

The NCCL apt package does not include Blackwell-specific (`compute_121`)
optimizations. Build from source on **both nodes**:

```bash
sudo apt-get install -y libopenmpi-dev

git clone -b v2.28.9-1 https://github.com/NVIDIA/nccl.git ~/nccl/
cd ~/nccl/
make -j src.build NVCC_GENCODE="-gencode=arch=compute_121,code=sm_121"
```

Build takes approximately 5-10 minutes. Confirm the library was built:

```bash
ls ~/nccl/build/lib/libnccl.so
```

### Build NCCL tests

```bash
git clone https://github.com/NVIDIA/nccl-tests.git ~/nccl-tests/
cd ~/nccl-tests/
CUDA_HOME=/usr/local/cuda \
MPI_HOME=/usr/lib/aarch64-linux-gnu/openmpi \
make -j MPI=1
```

Confirm the test binary was built:

```bash
ls ~/nccl-tests/build/all_gather_perf
```

---

## Step 5 - Run NCCL Bandwidth Test

Set the required environment variables on **both nodes** (add to `~/.bashrc` or
`/etc/profile.d/nccl.sh` to persist):

```bash
export NCCL_HOME="$HOME/nccl/build"
export CUDA_HOME="/usr/local/cuda"
export MPI_HOME="/usr/lib/aarch64-linux-gnu/openmpi"
export LD_LIBRARY_PATH="$NCCL_HOME/lib:$CUDA_HOME/lib64:$MPI_HOME/lib:$LD_LIBRARY_PATH"
```

Find the active interface and its IP on each node:

```bash
# Check which interface is Up
ibdev2netdev

# Get the link-local IP of the Up interface (e.g. enp1s0f1np1)
ip -4 addr show enp1s0f1np1
```

Set the interface name (use the interface that is `Up` from `ibdev2netdev`):

```bash
export CX7_IFACE=enp1s0f1np1   # replace with your Up interface
export UCX_NET_DEVICES=$CX7_IFACE
export NCCL_SOCKET_IFNAME=$CX7_IFACE
export OMPI_MCA_btl_tcp_if_include=$CX7_IFACE
```

Run the `all_gather` performance test from **node 1** (replace IPs):

```bash
mpirun -np 2 \
  -H <node1-cx7-ip>:1,<node2-cx7-ip>:1 \
  --mca plm_rsh_agent "ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no" \
  -x LD_LIBRARY_PATH=$LD_LIBRARY_PATH \
  -x NCCL_SOCKET_IFNAME=$NCCL_SOCKET_IFNAME \
  -x UCX_NET_DEVICES=$UCX_NET_DEVICES \
  ~/nccl-tests/build/all_gather_perf -b 16G -e 16G -f 2
```

Expected output (200 Gbps = ~25 GB/s):

```terminal
#                                                              out-of-place                       in-place
#       size         count      type   redop    root     time   algbw   busbw #wrong     time   algbw   busbw #wrong
    17179869184   4294967296     float    none      -1   2746.8   6.25   3.13      0   2742.3   6.26   3.13      0
```

> `busbw` near 100 Gbps (3.13 GB/s per direction) confirms the 200 Gbps link
> is working correctly. NCCL reports half the wire bandwidth for all_gather
> due to the algorithm's communication pattern.

---

## Step 6 - (Optional) RDMA Bandwidth Test

Validates the raw RoCE fabric layer, independent of NCCL:

```bash
sudo apt-get install -y perftest
```

On **node 1** (server):

```bash
ib_write_bw -d rocep1s0f0 -i 1 -p 12000 -F --report_gbits --run_infinitely
```

On **node 2** (client), replace with node 1's link-local IP:

```bash
ib_write_bw -d rocep1s0f0 -i 1 -p 12000 -F --report_gbits <node1-cx7-ip> --run_infinitely
```

Expected bandwidth: ~92-100 Gbps per port. Two ports combined: ~185-200 Gbps total.

> Use `ibdev2netdev` to find your actual RDMA device names (`rocep1s0f0`, etc.).

---

## NCCL Environment Variables Reference

| Variable                    | Value                      | Purpose                                      |
|-----------------------------|----------------------------|----------------------------------------------|
| `NCCL_HOME`                 | `~/nccl/build`             | Path to custom-built NCCL                    |
| `NCCL_SOCKET_IFNAME`        | `enp1s0f1np1` (or active)  | Which interface NCCL uses for communication  |
| `UCX_NET_DEVICES`           | `enp1s0f1np1` (or active)  | UCX transport device                         |
| `OMPI_MCA_btl_tcp_if_include` | `enp1s0f1np1` (or active) | MPI TCP transport interface                  |
| `NCCL_DEBUG`                | `INFO` (optional)          | Verbose NCCL logging for debugging           |
| `NCCL_IB_DISABLE`           | `0` (default)              | Keep at 0 to enable RoCE over CX-7           |

---

## Next Step

Both nodes are now ready for multi-node distributed workloads. See the
[DGX Spark Performance Benchmarking Guide](https://github.com/NVIDIA/dgx-spark-playbooks/blob/main/nvidia/connect-two-sparks/assets/performance_benchmarking_guide.md)
for TensorRT-LLM, vLLM, and SGLang multi-node inference benchmarks.
