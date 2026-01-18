#!/usr/bin/env python3
"""
Cortex Model Lifecycle Manager

Manages LLM models as first-class system services using systemd.
"""

import json
import sqlite3
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

CORTEX_DB_PATH = Path.home() / ".cortex/models.db"
CORTEX_SERVICE_DIR = Path.home() / ".config/systemd/user"


@dataclass
class ModelConfig:
    name: str
    model_path: str
    backend: str = "vllm"
    port: int = 8000
    gpu_memory_fraction: float = 0.9
    max_model_len: int = 4096
    gpu_ids: list[int] = field(default_factory=lambda: [0])
    memory_limit: str = "32G"
    cpu_limit: float = 4.0
    restart_policy: str = "on-failure"
    preload_on_boot: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelConfig":
        return cls(**data)


class ModelDatabase:
    def __init__(self):
        CORTEX_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(CORTEX_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    name TEXT PRIMARY KEY,
                    config TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def save_model(self, config: ModelConfig):
        with sqlite3.connect(CORTEX_DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO models VALUES (?, ?, ?)",
                (config.name, json.dumps(config.to_dict()), datetime.utcnow().isoformat()),
            )

    def get_model(self, name: str) -> ModelConfig | None:
        with sqlite3.connect(CORTEX_DB_PATH) as conn:
            row = conn.execute("SELECT config FROM models WHERE name = ?", (name,)).fetchone()
            return ModelConfig.from_dict(json.loads(row[0])) if row else None

    def list_models(self) -> list[ModelConfig]:
        with sqlite3.connect(CORTEX_DB_PATH) as conn:
            rows = conn.execute("SELECT config FROM models").fetchall()
            return [ModelConfig.from_dict(json.loads(r[0])) for r in rows]

    def delete_model(self, name: str):
        with sqlite3.connect(CORTEX_DB_PATH) as conn:
            conn.execute("DELETE FROM models WHERE name = ?", (name,))


class ServiceGenerator:
    BACKENDS = {
        "vllm": "python -m vllm.entrypoints.openai.api_server --model {model_path} --port {port}",
        "llamacpp": "llama-server -m {model_path} --port {port}",
        "ollama": "ollama serve",
    }

    def generate(self, config: ModelConfig) -> str:
        cmd = self.BACKENDS.get(config.backend, self.BACKENDS["vllm"]).format(**asdict(config))
        return f"""[Unit]
Description=Cortex Model: {config.name}
After=network.target

[Service]
Type=simple
ExecStart={cmd}
Environment=CUDA_VISIBLE_DEVICES={",".join(map(str, config.gpu_ids))}
CPUQuota={int(config.cpu_limit * 100)}%
MemoryMax={config.memory_limit}
Restart={config.restart_policy}
NoNewPrivileges=true

[Install]
WantedBy=default.target
"""


class ModelLifecycleManager:
    def __init__(self):
        self.db = ModelDatabase()
        CORTEX_SERVICE_DIR.mkdir(parents=True, exist_ok=True)

    def _systemctl(self, *args):
        return subprocess.run(["systemctl", "--user"] + list(args), capture_output=True, text=True)

    def register(self, config: ModelConfig) -> bool:
        service = ServiceGenerator().generate(config)
        service_path = CORTEX_SERVICE_DIR / f"cortex-{config.name}.service"
        service_path.write_text(service)
        self.db.save_model(config)
        self._systemctl("daemon-reload")
        print(f"✅ Registered model '{config.name}'")
        return True

    def start(self, name: str) -> bool:
        result = self._systemctl("start", f"cortex-{name}.service")
        print(f"{'✅' if result.returncode == 0 else '❌'} Start {name}: {result.stderr or 'OK'}")
        return result.returncode == 0

    def stop(self, name: str) -> bool:
        result = self._systemctl("stop", f"cortex-{name}.service")
        print(f"{'✅' if result.returncode == 0 else '❌'} Stop {name}")
        return result.returncode == 0

    def status(self, name: str = None):
        models = [self.db.get_model(name)] if name else self.db.list_models()
        print(f"\n{'NAME':<20} {'STATE':<12} {'BACKEND':<10}")
        print("-" * 50)
        for m in models:
            if m:
                result = self._systemctl("is-active", f"cortex-{m.name}.service")
                state = result.stdout.strip() or "unknown"
                print(f"{m.name:<20} {state:<12} {m.backend:<10}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Cortex Model Lifecycle Manager")
    sub = parser.add_subparsers(dest="cmd")

    reg = sub.add_parser("register")
    reg.add_argument("name")
    reg.add_argument("--path", required=True)
    reg.add_argument("--backend", default="vllm")
    reg.add_argument("--port", type=int, default=8000)
    reg.add_argument("--gpus", default="0")

    for cmd in ["start", "stop", "unregister"]:
        p = sub.add_parser(cmd)
        p.add_argument("name")

    sub.add_parser("status").add_argument("name", nargs="?")
    sub.add_parser("list")

    args = parser.parse_args()
    mgr = ModelLifecycleManager()

    if args.cmd == "register":
        mgr.register(
            ModelConfig(
                args.name,
                args.path,
                args.backend,
                args.port,
                gpu_ids=[int(x) for x in args.gpus.split(",")],
            )
        )
    elif args.cmd == "start":
        mgr.start(args.name)
    elif args.cmd == "stop":
        mgr.stop(args.name)
    elif args.cmd in ("status", "list"):
        mgr.status(getattr(args, "name", None))


if __name__ == "__main__":
    main()
