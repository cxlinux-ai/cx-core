"""
Stack command: Pre-built package combinations
Usage:
  cortex stack --list              # List all stacks
  cortex stack ml                  # Install ML stack (auto-detects GPU)
  cortex stack ml-cpu              # Install CPU-only version
  cortex stack webdev --dry-run    # Preview webdev stack
"""

import json
import threading
from pathlib import Path
from typing import Any

from cortex.hardware_detection import has_nvidia_gpu


class StackManager:
    """Manages pre-built package stacks with hardware awareness"""

    def __init__(self) -> None:
        # stacks.json is in the same directory as this file (cortex/)
        self.stacks_file = Path(__file__).parent / "stacks.json"
        self._stacks = None
        self._stacks_lock = threading.Lock()  # Protect _stacks cache

    def load_stacks(self) -> dict[str, Any]:
        """Load stacks from JSON file (thread-safe)"""
        # Fast path: check without lock
        if self._stacks is not None:
            return self._stacks

        # Slow path: acquire lock and recheck
        with self._stacks_lock:
            if self._stacks is not None:
                return self._stacks

            try:
                with open(self.stacks_file) as f:
                    self._stacks = json.load(f)
                return self._stacks
            except FileNotFoundError as e:
                raise FileNotFoundError(f"Stacks config not found at {self.stacks_file}") from e
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in {self.stacks_file}") from e

    def list_stacks(self) -> list[dict[str, Any]]:
        """Get all available stacks"""
        stacks = self.load_stacks()
        return stacks.get("stacks", [])

    def find_stack(self, stack_id: str) -> dict[str, Any] | None:
        """Find a stack by ID"""
        for stack in self.list_stacks():
            if stack["id"] == stack_id:
                return stack
        return None

    def get_stack_packages(self, stack_id: str) -> list[str]:
        """Get package list for a stack"""
        stack = self.find_stack(stack_id)
        return stack.get("packages", []) if stack else []

    def suggest_stack(self, base_stack: str) -> str:
        """
        Suggest hardware-appropriate stack variant.
        For the 'ml' stack, returns 'ml' if a GPU is detected, otherwise 'ml-cpu'.
        Other stacks are returned unchanged.

        Args:
        base_stack: The requested stack identifier.

        Returns:
        The suggested stack identifier (may differ from input).
        """
        if base_stack == "ml":
            return "ml" if has_nvidia_gpu() else "ml-cpu"
        return base_stack

    def describe_stack(self, stack_id: str) -> str:
        """
        Generate a formatted description of a stack.

        Args:
            stack_id: The stack identifier to describe.

        Returns:
            A multi-line formatted string with stack name, description,
            packages, tags, and hardware requirements. Returns a not-found
            message if the stack doesn't exist.
        """
        stack = self.find_stack(stack_id)
        if not stack:
            return f"Stack '{stack_id}' not found"

        output = f"\n📦 Stack: {stack['name']}\n"
        output += f"Description: {stack['description']}\n\n"
        output += "Packages included:\n"

        for idx, pkg in enumerate(stack.get("packages", []), 1):
            output += f"  {idx}. {pkg}\n"

        tags = stack.get("tags", [])
        if tags:
            output += f"\nTags:  {', '.join(tags)}\n"

        hardware = stack.get("hardware", "any")
        output += f"Hardware: {hardware}\n"

        return output
