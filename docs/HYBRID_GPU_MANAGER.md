# Hybrid GPU Manager Module

**Issue:** Hybrid GPU (Intel/AMD + NVIDIA) switching causes latency and stuttering  
**Status:** Ready for Review  
**Scope:** Hybrid GPU Manager (state + per-app + switching + battery estimates)

## Overview

Hybrid GPU laptops can stutter when the wrong GPU mode is active (e.g., NVIDIA always-on) or when apps launch on an unintended GPU. This module adds a **hybrid GPU manager** to Cortex that:

- Detects current GPU state (Integrated / Hybrid / NVIDIA)
- Supports per-app GPU assignment (run specific apps on NVIDIA or Integrated)
- Supports easy switching between modes (via supported backends)
- Estimates battery impact (heuristic + optional measurements when available)

## Features

| Feature                  | Description                                                                       |
| ------------------------ | --------------------------------------------------------------------------------- |
| GPU State Detection      | Detects current mode: `Integrated`, `Hybrid`, or `NVIDIA`                         |
| Switch Backend Detection | Detects supported switch tooling: `prime-select`, `system76-power`                |
| Mode Switch Planning     | Produces a safe plan (commands + restart requirement)                             |
| Mode Switch Execution    | Executes switch commands (sudo) with opt-in confirmation                          |
| Per-App GPU Assignment   | Stores app → GPU preference in `config.yaml`                                      |
| GPU Run (Env Injection)  | Runs a command with GPU env vars applied (`--nvidia`, `--integrated`, `--app`)    |
| Battery Impact Estimates | Heuristic power/impact + best-effort measured NVIDIA power draw / battery metrics |

______________________________________________________________________

## Quick Start

### 1) Show current GPU status

```bash
cortex gpu status
```

Expected output includes:

- GPU mode (Integrated/Hybrid/NVIDIA)
- Switch backend (prime-select / system76-power / none)
- Per-app assignment count

### 2) Set per-app GPU preference (persisted)

```bash
export CORTEX_CONFIG_DIR="$(mktemp -d)"
echo "Using CORTEX_CONFIG_DIR=$CORTEX_CONFIG_DIR"

cortex gpu app set blender nvidia
cortex gpu app get blender
cortex gpu app list

echo "--- config.yaml (persist evidence) ---"
cat "$CORTEX_CONFIG_DIR/config.yaml"
```

### 3) Run a command with GPU env injected

```bash
# Force integrated
cortex gpu run --integrated -- bash -lc 'echo "__NV_PRIME_RENDER_OFFLOAD=${__NV_PRIME_RENDER_OFFLOAD:-empty}"; echo "__GLX_VENDOR_LIBRARY_NAME=${__GLX_VENDOR_LIBRARY_NAME:-empty}"'

# Force nvidia
cortex gpu run --nvidia -- bash -lc 'echo "__NV_PRIME_RENDER_OFFLOAD=${__NV_PRIME_RENDER_OFFLOAD:-empty}"; echo "__GLX_VENDOR_LIBRARY_NAME=${__GLX_VENDOR_LIBRARY_NAME:-empty}"'

# Per-app assignment -> run --app
cortex gpu app set blender nvidia
cortex gpu run --app blender -- bash -lc 'echo "__NV_PRIME_RENDER_OFFLOAD=${__NV_PRIME_RENDER_OFFLOAD:-empty}"; echo "__GLX_VENDOR_LIBRARY_NAME=${__GLX_VENDOR_LIBRARY_NAME:-empty}"'
```

### 4) Battery impact estimates

```bash
cortex gpu-battery
# or measured-only:
cortex gpu-battery --measured-only
```

______________________________________________________________________

## CLI Usage

### GPU status

```bash
cortex gpu status
```

### GPU switching

```bash
# Dry-run: show what would be executed
cortex gpu set integrated --dry-run
cortex gpu set hybrid --dry-run
cortex gpu set nvidia --dry-run

# Execute: actually run (sudo)
cortex gpu set hybrid --execute
# Skip confirmation:
cortex gpu set hybrid --execute --yes
```

**Note:** switching often requires a reboot or logout/login (reported as `Restart required: True`).

### Per-app assignment

```bash
cortex gpu app set <app> nvidia|integrated
cortex gpu app get <app>
cortex gpu app list
cortex gpu app remove <app>
```

### Run with GPU preference (env injection)

```bash
# Explicit override
cortex gpu run --nvidia -- <cmd...>
cortex gpu run --integrated -- <cmd...>

# Per-app preference
cortex gpu run --app <app> -- <cmd...>
```

______________________________________________________________________

## Configuration

Per-app preferences are stored under the user config dir (respects `CORTEX_CONFIG_DIR`):

```yaml
gpu:
  apps:
    blender: nvidia
    obs: integrated
```

To prove persistence in review videos, use:

```bash
export CORTEX_CONFIG_DIR="$(mktemp -d)"
echo "Using CORTEX_CONFIG_DIR=$CORTEX_CONFIG_DIR"
ls -la "$CORTEX_CONFIG_DIR" || true
cat "$CORTEX_CONFIG_DIR/config.yaml" || true
```

______________________________________________________________________

## API Reference

### detect_gpu_mode()

Detects current GPU mode and returns one of:

- `"Integrated"`
- `"Hybrid"`
- `"NVIDIA"`

```python
from cortex.hardware_detection import detect_gpu_mode

mode = detect_gpu_mode()
print(mode)
```

### detect_gpu_switch_backend()

Detects which backend can perform a mode switch.

```python
from cortex.gpu_manager import detect_gpu_switch_backend

backend = detect_gpu_switch_backend()
print(backend.value)  # e.g. "prime-select"
```

### plan_gpu_mode_switch(mode)

Creates a plan describing what commands would be executed and whether a restart is required.

```python
from cortex.gpu_manager import plan_gpu_mode_switch

plan = plan_gpu_mode_switch("hybrid")
print(plan.backend.value)
print(plan.target_mode)
print(plan.commands)
print(plan.requires_restart)
```

### apply_gpu_mode_switch(plan, execute=True)

Executes the switch plan (runs the commands).

```python
from cortex.gpu_manager import plan_gpu_mode_switch, apply_gpu_mode_switch

plan = plan_gpu_mode_switch("hybrid")
apply_gpu_mode_switch(plan, execute=True)
```

### Per-app preference helpers

```python
from cortex.gpu_manager import (
  set_app_gpu_preference, get_app_gpu_preference,
  list_app_gpu_preferences, remove_app_gpu_preference,
)

set_app_gpu_preference("blender", "nvidia")
print(get_app_gpu_preference("blender"))

print(list_app_gpu_preferences())
remove_app_gpu_preference("blender")
```

### GPU env injection

```python
from cortex.gpu_manager import get_per_app_gpu_env, run_command_with_env

env = get_per_app_gpu_env(use_nvidia=True)   # or use_nvidia=False
run_command_with_env(["bash", "-lc", "env | grep -E '__NV_|__GLX_'"], extra_env=env)
```

### estimate_gpu_battery_impact()

Returns structured data:

```python
from cortex.hardware_detection import estimate_gpu_battery_impact

data = estimate_gpu_battery_impact()
print(data["mode"])       # Integrated | Hybrid | NVIDIA
print(data["current"])    # integrated | hybrid_idle | nvidia_active
print(data["estimates"])  # heuristic table
print(data.get("measured", {}))
```

______________________________________________________________________

## Switching Backends

### prime-select (Ubuntu / NVIDIA PRIME)

Planned commands:

- Integrated: `sudo prime-select intel`
- Hybrid (on-demand): `sudo prime-select on-demand`
- NVIDIA: `sudo prime-select nvidia`

### system76-power (System76 / Pop!_OS)

Planned commands depend on the system76-power CLI modes supported by the distro.

______________________________________________________________________

## Testing

### Unit tests

Run these locally:

```bash
pytest -q tests/test_gpu_manager.py
pytest -q tests/test_hybrid_gpu_manager.py

# verbose
pytest -vv tests/test_gpu_manager.py -rA
pytest -vv tests/test_hybrid_gpu_manager.py -rA
```

What these tests cover:

- Backend detection (prime-select / system76-power)
- Mode switch planning (commands, restart requirement, invalid mode raises)
- Env merging and per-app config roundtrip
- Hybrid GPU mode detection safety + battery estimation structure

### CLI / reviewer video scripts

```bash
set -euo pipefail

echo "=== VIDEO 1: VERSION + ENV ==="
which cortex || true
cortex --version || true
python3 --version
pytest --version

echo
echo "=== VIDEO 2: COLLECT GPU TESTS (prove no missing tests) ==="
pytest --collect-only -q | grep -i gpu || true

echo
echo "=== VIDEO 3: RUN UNIT TESTS (GPU MANAGER) ==="
pytest -vv tests/test_gpu_manager.py -rA

echo
echo "=== VIDEO 4: RUN UNIT TESTS (HYBRID GPU DETECTION + BATTERY) ==="
pytest -vv tests/test_hybrid_gpu_manager.py -rA

echo
echo "=== VIDEO 5: GPU STATUS (current state + backend + assignments count) ==="
cortex gpu status

echo
echo "=== VIDEO 6: BATTERY IMPACT ESTIMATION (heuristic + measured if available) ==="
cortex gpu-battery || true
echo "--- measured only ---"
cortex gpu-battery --measured-only || true

echo
echo "=== VIDEO 7: PER-APP ASSIGNMENT (persist evidence) ==="
export CORTEX_CONFIG_DIR="$(mktemp -d)"
echo "Using CORTEX_CONFIG_DIR=$CORTEX_CONFIG_DIR"

cortex gpu app set blender nvidia
cortex gpu app get blender
cortex gpu app list

echo "--- config.yaml (persist evidence) ---"
ls -la "$CORTEX_CONFIG_DIR" || true
cat "$CORTEX_CONFIG_DIR/config.yaml" || true

cortex gpu app remove blender
cortex gpu app get blender || true

echo
echo "=== VIDEO 8: GPU RUN (ENV INJECTION) ==="
export CORTEX_CONFIG_DIR="$(mktemp -d)"
echo "Using CORTEX_CONFIG_DIR=$CORTEX_CONFIG_DIR"

echo "--- override integrated ---"
cortex gpu run --integrated -- bash -lc 'echo "__NV_PRIME_RENDER_OFFLOAD=${__NV_PRIME_RENDER_OFFLOAD:-empty}"; echo "__GLX_VENDOR_LIBRARY_NAME=${__GLX_VENDOR_LIBRARY_NAME:-empty}"'

echo "--- override nvidia ---"
cortex gpu run --nvidia -- bash -lc 'echo "__NV_PRIME_RENDER_OFFLOAD=${__NV_PRIME_RENDER_OFFLOAD:-empty}"; echo "__GLX_VENDOR_LIBRARY_NAME=${__GLX_VENDOR_LIBRARY_NAME:-empty}"'

echo "--- per-app assignment -> run --app ---"
cortex gpu app set blender nvidia
cortex gpu run --app blender -- bash -lc 'echo "__NV_PRIME_RENDER_OFFLOAD=${__NV_PRIME_RENDER_OFFLOAD:-empty}"; echo "__GLX_VENDOR_LIBRARY_NAME=${__GLX_VENDOR_LIBRARY_NAME:-empty}"'

echo
echo "=== VIDEO 9: SWITCHING (DRY-RUN + EXECUTE PATH WITH FAKE BACKEND) ==="
cortex gpu set integrated --dry-run || true
cortex gpu set hybrid --dry-run || true
cortex gpu set nvidia --dry-run || true

echo "--- fake backend to prove execute path runs sudo/prime-select ---"
FAKEBIN="$(mktemp -d)"
echo "Using FAKEBIN=$FAKEBIN"

cat >"$FAKEBIN/sudo" <<'EOF'
#!/usr/bin/env bash
echo "[fake sudo] $@" >&2
exec "$@"
EOF
chmod +x "$FAKEBIN/sudo"

cat >"$FAKEBIN/prime-select" <<'EOF'
#!/usr/bin/env bash
echo "[fake prime-select] called with: $@" >&2
exit 0
EOF
chmod +x "$FAKEBIN/prime-select"

export PATH="$FAKEBIN:$PATH"

cortex gpu status
cortex gpu set hybrid --dry-run
cortex gpu set hybrid --execute --yes

echo
echo "=== BONUS: NEGATIVE TESTS (validation should reject invalid choices) ==="
cortex gpu set turbo --dry-run || true
cortex gpu app set blender turbo || true

echo
echo "=== DONE ==="
```

______________________________________________________________________

## Notes / Limitations

- Battery *measurements* depend on system support (WSL often can’t read Linux battery metrics).
- Switching modes usually requires a reboot or logout/login.
- On systems without a supported backend, switching returns a “no supported backend” message (status still works).

______________________________________________________________________

**Closes:** Hybrid GPU Manager scope (state + per-app + switching + battery estimates)
