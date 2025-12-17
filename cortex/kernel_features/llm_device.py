#!/usr/bin/env python3
"""
Cortex /dev/llm Virtual Device

FUSE-based LLM interface - everything is a file.
"""

import errno
import json
import os
import stat
import time
from dataclasses import dataclass, field

try:
    from fuse import FUSE, FuseOSError, Operations

    HAS_FUSE = True
except ImportError:
    HAS_FUSE = False

    class FuseOSError(Exception):
        def __init__(self, e):
            self.errno = e

    class Operations:
        pass


try:
    import anthropic

    HAS_API = True
except ImportError:
    HAS_API = False


@dataclass
class Session:
    id: str
    model: str
    messages: list[dict] = field(default_factory=list)
    prompt: str = ""
    response: str = ""
    temp: float = 0.7
    max_tokens: int = 4096


class MockLLM:
    def complete(self, model, messages, max_tokens, temp, system=None):
        return f"[Mock] Response to: {messages[-1]['content'][:50]}..."


class LLMDevice(Operations):
    MODELS = {"claude": "claude-3-sonnet-20240229", "sonnet": "claude-3-5-sonnet-20241022"}

    def __init__(self):
        self.sessions: dict[str, Session] = {"default": Session("default", "claude")}
        self.llm = (
            anthropic.Anthropic() if HAS_API and os.environ.get("ANTHROPIC_API_KEY") else MockLLM()
        )
        self.start = time.time()
        self.requests = 0

    def _parse(self, path):
        parts = path.strip("/").split("/")
        if not parts[0]:
            return ("root", None, None)
        if parts[0] in self.MODELS:
            return ("model", parts[0], parts[1] if len(parts) > 1 else None)
        if parts[0] == "sessions":
            return (
                "session",
                parts[1] if len(parts) > 1 else None,
                parts[2] if len(parts) > 2 else None,
            )
        if parts[0] == "status":
            return ("status", None, None)
        return ("unknown", None, None)

    def getattr(self, path, fh=None):
        t, m, f = self._parse(path)
        now = time.time()
        if t in ("root", "model", "session") and not f:
            return {
                "st_mode": stat.S_IFDIR | 0o755,
                "st_nlink": 2,
                "st_uid": os.getuid(),
                "st_gid": os.getgid(),
                "st_atime": now,
                "st_mtime": now,
                "st_ctime": now,
            }
        if f or t == "status":
            return {
                "st_mode": stat.S_IFREG | 0o644,
                "st_nlink": 1,
                "st_uid": os.getuid(),
                "st_gid": os.getgid(),
                "st_size": 0,
                "st_atime": now,
                "st_mtime": now,
                "st_ctime": now,
            }
        raise FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        t, m, f = self._parse(path)
        base = [".", ".."]
        if t == "root":
            return base + list(self.MODELS.keys()) + ["sessions", "status"]
        if t == "model":
            return base + ["prompt", "response", "config"]
        if t == "session" and not m:
            return base + list(self.sessions.keys())
        if t == "session" and m:
            return base + ["prompt", "response", "history"]
        return base

    def read(self, path, size, offset, fh):
        t, m, f = self._parse(path)
        s = self.sessions.get("default")
        if t == "model" and f == "response":
            return s.response.encode()[offset : offset + size]
        if t == "status":
            return json.dumps(
                {"status": "running", "uptime": time.time() - self.start, "requests": self.requests}
            ).encode()[offset : offset + size]
        return b""

    def write(self, path, data, offset, fh):
        t, m, f = self._parse(path)
        if t == "model" and f == "prompt":
            s = self.sessions["default"]
            s.prompt = data.decode().strip()
            s.messages.append({"role": "user", "content": s.prompt})
            try:
                resp = (
                    self.llm.messages.create(
                        model=self.MODELS.get(m, "claude-3-sonnet-20240229"),
                        max_tokens=s.max_tokens,
                        messages=s.messages,
                    )
                    if HAS_API
                    else self.llm.complete(m, s.messages, s.max_tokens, s.temp)
                )
                s.response = resp.content[0].text if HAS_API else resp
            except Exception as e:
                s.response = f"Error: {e}"
            s.messages.append({"role": "assistant", "content": s.response})
            self.requests += 1
            return len(data)
        raise FuseOSError(errno.EACCES)

    def truncate(self, path, length, fh=None):
        return 0

    def open(self, path, flags):
        return 0

    def create(self, path, mode, fi=None):
        return 0


def mount(mountpoint, foreground=False):
    if not HAS_FUSE:
        print("Install fusepy: pip install fusepy")
        return
    from pathlib import Path

    Path(mountpoint).mkdir(parents=True, exist_ok=True)
    print(f"Mounting /dev/llm at {mountpoint}")
    print(f'Usage: echo "Hello" > {mountpoint}/claude/prompt && cat {mountpoint}/claude/response')
    FUSE(LLMDevice(), mountpoint, foreground=foreground, allow_other=False)


def main():
    import argparse

    p = argparse.ArgumentParser(description="Cortex /dev/llm Device")
    sub = p.add_subparsers(dest="cmd")
    m = sub.add_parser("mount")
    m.add_argument("mountpoint")
    m.add_argument("-f", "--foreground", action="store_true")
    sub.add_parser("umount").add_argument("mountpoint")

    args = p.parse_args()
    if args.cmd == "mount":
        mount(args.mountpoint, args.foreground)
    elif args.cmd == "umount":
        import subprocess

        subprocess.run(["fusermount", "-u", args.mountpoint])


if __name__ == "__main__":
    main()
