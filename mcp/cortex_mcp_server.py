#!/usr/bin/env python3
"""
Cortex Linux MCP Server

Model Context Protocol server for AI-native package management.
Connects Claude, ChatGPT, Cursor, VS Code to Cortex Linux.
"""

import asyncio
import json
import logging
import subprocess
from datetime import datetime

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp[cli]")
    import sys

    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cortex-mcp")

SERVER_NAME = "cortex-linux"
SERVER_VERSION = "1.0.0"


class CortexMCPServer:
    def __init__(self):
        self.server = Server(SERVER_NAME)
        self._setup_handlers()
        self._cortex_path = self._find_cortex()

    def _find_cortex(self) -> str:
        result = subprocess.run(["which", "cortex"], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else "cortex"

    def _setup_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            return ListToolsResult(
                tools=[
                    Tool(
                        name="install_package",
                        description="Install packages using natural language. Safe dry-run by default.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "request": {
                                    "type": "string",
                                    "description": "Package name or description",
                                },
                                "dry_run": {"type": "boolean", "default": True},
                                "optimize_hardware": {"type": "boolean", "default": True},
                            },
                            "required": ["request"],
                        },
                    ),
                    Tool(
                        name="search_packages",
                        description="Search for packages by name or description.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "limit": {"type": "integer", "default": 10},
                            },
                            "required": ["query"],
                        },
                    ),
                    Tool(
                        name="get_history",
                        description="Get installation history with rollback IDs.",
                        inputSchema={
                            "type": "object",
                            "properties": {"limit": {"type": "integer", "default": 10}},
                        },
                    ),
                    Tool(
                        name="rollback",
                        description="Rollback a previous installation.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "installation_id": {"type": "string"},
                                "dry_run": {"type": "boolean", "default": True},
                            },
                            "required": ["installation_id"],
                        },
                    ),
                    Tool(
                        name="detect_hardware",
                        description="Detect GPU/CPU and get optimization recommendations.",
                        inputSchema={"type": "object", "properties": {}},
                    ),
                    Tool(
                        name="system_status",
                        description="Get system disk space, packages, and updates.",
                        inputSchema={"type": "object", "properties": {}},
                    ),
                ]
            )

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            try:
                if name == "install_package":
                    result = await self._install_package(
                        arguments.get("request", ""),
                        arguments.get("dry_run", True),
                        arguments.get("optimize_hardware", True),
                    )
                elif name == "search_packages":
                    result = await self._search_packages(
                        arguments.get("query", ""), arguments.get("limit", 10)
                    )
                elif name == "get_history":
                    result = await self._get_history(arguments.get("limit", 10))
                elif name == "rollback":
                    result = await self._rollback(
                        arguments.get("installation_id", ""), arguments.get("dry_run", True)
                    )
                elif name == "detect_hardware":
                    result = await self._detect_hardware()
                elif name == "system_status":
                    result = await self._system_status()
                else:
                    result = {"error": f"Unknown tool: {name}"}

                return CallToolResult(
                    content=[
                        TextContent(type="text", text=json.dumps(result, indent=2, default=str))
                    ]
                )
            except Exception as e:
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps({"error": str(e)}))],
                    isError=True,
                )

    async def _run_cortex(self, args: list[str]) -> dict:
        cmd = [self._cortex_path] + args
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return {
                "success": process.returncode == 0,
                "stdout": stdout.decode("utf-8"),
                "stderr": stderr.decode("utf-8"),
            }
        except FileNotFoundError:
            return {"success": False, "error": "Cortex CLI not found"}

    async def _install_package(
        self, request: str, dry_run: bool = True, optimize: bool = True
    ) -> dict:
        args = ["install", request, "--dry-run" if dry_run else "--execute"]
        if optimize:
            args.append("--optimize")
        result = await self._run_cortex(args)
        return {"mode": "dry_run" if dry_run else "execute", "request": request, **result}

    async def _search_packages(self, query: str, limit: int = 10) -> dict:
        process = await asyncio.create_subprocess_exec(
            "apt-cache",
            "search",
            query,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        lines = stdout.decode("utf-8").strip().split("\n")[:limit]
        packages = [
            {"name": l.split(" - ")[0], "description": l.split(" - ")[1]}
            for l in lines
            if " - " in l
        ]
        return {"query": query, "count": len(packages), "packages": packages}

    async def _get_history(self, limit: int = 10) -> dict:
        result = await self._run_cortex(["history", "--limit", str(limit)])
        return {"limit": limit, **result}

    async def _rollback(self, installation_id: str, dry_run: bool = True) -> dict:
        args = ["rollback", installation_id]
        if dry_run:
            args.append("--dry-run")
        result = await self._run_cortex(args)
        return {
            "installation_id": installation_id,
            "mode": "dry_run" if dry_run else "execute",
            **result,
        }

    async def _detect_hardware(self) -> dict:
        hardware = {}
        try:
            # Use async file reading via asyncio
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(
                None, lambda: open("/proc/cpuinfo").read()
            )
            for line in content.split("\n"):
                if line.startswith("model name"):
                    hardware["cpu"] = line.split(":")[1].strip()
                    break
        except Exception:
            hardware["cpu"] = "Unknown"

        try:
            process = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=name",
                "--format=csv,noheader",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                hardware["gpu"] = stdout.decode("utf-8").strip()
        except Exception:
            hardware["gpu"] = None

        return hardware

    async def _system_status(self) -> dict:
        status = {"timestamp": datetime.now().isoformat()}
        process = await asyncio.create_subprocess_exec(
            "df", "-h", "/", stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        lines = stdout.decode("utf-8").strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            status["disk"] = {"total": parts[1], "used": parts[2], "available": parts[3]}
        return status

    async def run(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream, write_stream, self.server.create_initialization_options()
            )


def main():
    asyncio.run(CortexMCPServer().run())


if __name__ == "__main__":
    main()
