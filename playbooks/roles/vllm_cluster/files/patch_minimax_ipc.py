#!/usr/bin/env python3
"""Runtime backport of vLLM PR #44983 for images built on vLLM v0.23.0.

v0.23.0 ships the MiniMax fused QK-RMSNorm path (PR #43410) WITHOUT a guard:
``MiniMaxText01RMSNormTP.__init__`` unconditionally allocates a Lamport
workspace whenever ``tp_world > 1``. That workspace exchanges CUDA IPC handles
(cudaIpcGetMemHandle / cudaIpcOpenMemHandle), which only work between GPUs that
share GPU P2P on the SAME node. Across nodes (multi-node TP on GB10/DGX Spark)
the peer handle is invalid and the kernel aborts with
``cudaErrorInvalidResourceHandle (400)``, killing model load.

Upstream PR #44983 (commit dc10e46, "[Bugfix] Fix minimax_qk_norm_fusion")
wraps the allocation in try/except and falls back to the portable NCCL
allreduce + RMSNorm path (``self.workspace = None`` -> _minimax_qk_norm_fallback).

This script applies that exact change in-place at container start. It is
idempotent and a no-op once the image is rebuilt against a vLLM that already
contains the fix. Remove this backport when the image picks up >= the fix.
"""

import importlib.util
import sys

OLD = """            self.workspace = get_allreduce_workspace(
                rank=self.tp_rank,
                world_size=self.tp_world,
                max_tokens=MINIMAX_QK_NORM_MAX_TOKEN_NUM,
                process_group=get_tp_group().cpu_group,
            )
"""

NEW = """            try:
                self.workspace = get_allreduce_workspace(
                    rank=self.tp_rank,
                    world_size=self.tp_world,
                    max_tokens=MINIMAX_QK_NORM_MAX_TOKEN_NUM,
                    process_group=get_tp_group().cpu_group,
                )
            except Exception as e:
                # vLLM PR #44983 backport: the Lamport workspace exchanges CUDA
                # IPC handles and needs GPU P2P (IPC peer access). That is
                # unavailable across nodes (multi-node TP on GB10) and on GPUs
                # with P2P disabled, so allocation raises. Fall back to the
                # eager NCCL allreduce + RMSNorm path instead of failing load.
                print(
                    "[patch_minimax_ipc] Lamport workspace init failed (%s); "
                    "falling back to NCCL allreduce + RMSNorm path." % e,
                    file=sys.stderr,
                )
                self.workspace = None
"""


def main() -> int:
    spec = importlib.util.find_spec(
        "vllm.model_executor.layers.minimax_rms_norm.rms_norm_tp"
    )
    if spec is None or not spec.origin:
        print("[patch_minimax_ipc] vLLM minimax rms_norm_tp not found; skipping.")
        return 0

    path = spec.origin
    src = open(path, encoding="utf-8").read()

    if "patch_minimax_ipc" in src or "except Exception as e:" in src:
        print("[patch_minimax_ipc] already patched (or upstream fix present); no-op.")
        return 0

    if OLD not in src:
        print(
            "[patch_minimax_ipc] expected workspace block not found in %s; "
            "image may already contain the upstream fix. Skipping." % path
        )
        return 0

    open(path, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
    print("[patch_minimax_ipc] applied PR #44983 IPC fallback to %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
