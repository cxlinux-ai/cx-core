#!/usr/bin/env python3
import os
import subprocess
import argparse
from pathlib import Path

def run(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return ""

def detect_gpus():
    gpus = run(["lspci"])
    has_nvidia = "NVIDIA" in gpus
    has_intel = "Intel" in gpus or "AMD" in gpus
    return has_intel, has_nvidia

def active_gpu():
    if run(["which", "nvidia-smi"]):
        usage = run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader"])
        if usage:
            return "NVIDIA (active)"
    return "Integrated (Intel/AMD)"

def list_nvidia_apps():
    if not run(["which", "nvidia-smi"]):
        return []
    out = run([
        "nvidia-smi",
        "--query-compute-apps=process_name",
        "--format=csv,noheader"
    ])
    return out.splitlines() if out else []

def battery_estimate(nvidia_active: bool):
    if not Path("/sys/class/power_supply").exists():
        return "Unknown"
    return "~3.5h (NVIDIA active)" if nvidia_active else "~6h (Integrated only)"

def run_app(app, gpu):
    env = os.environ.copy()
    if gpu == "nvidia":
        env["__NV_PRIME_RENDER_OFFLOAD"] = "1"
        env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
        env["__VK_LAYER_NV_optimus"] = "NVIDIA_only"
    subprocess.Popen([app], env=env)

def main():
    parser = argparse.ArgumentParser(description="Hybrid GPU Manager (Linux)")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status")
    sub.add_parser("apps")

    runp = sub.add_parser("run")
    runp.add_argument("app")
    runp.add_argument("--gpu", choices=["intel", "nvidia"], default="intel")

    args = parser.parse_args()

    if args.cmd == "status":
        intel, nvidia = detect_gpus()
        active = active_gpu()
        print(f"Detected GPUs: Intel/AMD={intel}, NVIDIA={nvidia}")
        print(f"Active GPU: {active}")
        print("Battery estimate:", battery_estimate("NVIDIA" in active))

    elif args.cmd == "apps":
        apps = list_nvidia_apps()
        if not apps:
            print("No apps using NVIDIA GPU")
        else:
            print("Apps using NVIDIA GPU:")
            for a in apps:
                print(" -", a)

    elif args.cmd == "run":
        print(f"Launching {args.app} on {args.gpu.upper()} GPU")
        run_app(args.app, args.gpu)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
