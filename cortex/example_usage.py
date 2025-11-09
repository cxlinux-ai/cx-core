#!/usr/bin/env python3
"""
Example usage of the PackageManager wrapper.

This demonstrates how to use the natural language package manager interface.

Run from project root:
    python3 cortex/example_usage.py
"""

import sys
import os

# Add parent directory to path to import cortex module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cortex.packages import PackageManager


def main():
    """Demonstrate PackageManager usage."""
    
    # Initialize package manager (auto-detects system)
    pm = PackageManager()
    
    print("=" * 60)
    print("Cortex Package Manager - Example Usage")
    print("=" * 60)
    print()
    
    # Example 1: Python with data science libraries (from requirements)
    print("Example 1: Install python with data science libraries")
    print("-" * 60)
    commands = pm.parse("install python with data science libraries")
    for cmd in commands:
        print(f"  $ {cmd}")
    print()
    
    # Example 2: Python development tools
    print("Example 2: Install python development tools")
    print("-" * 60)
    commands = pm.parse("install python development tools")
    for cmd in commands:
        print(f"  $ {cmd}")
    print()
    
    # Example 3: Docker
    print("Example 3: Install docker")
    print("-" * 60)
    commands = pm.parse("install docker")
    for cmd in commands:
        print(f"  $ {cmd}")
    print()
    
    # Example 4: Multiple packages
    print("Example 4: Install git with build tools")
    print("-" * 60)
    commands = pm.parse("install git with build tools")
    for cmd in commands:
        print(f"  $ {cmd}")
    print()
    
    # Example 5: Web server stack
    print("Example 5: Install nginx with mysql and redis")
    print("-" * 60)
    commands = pm.parse("install nginx with mysql and redis")
    for cmd in commands:
        print(f"  $ {cmd}")
    print()
    
    # Example 6: Remove packages
    print("Example 6: Remove python")
    print("-" * 60)
    commands = pm.parse("remove python")
    for cmd in commands:
        print(f"  $ {cmd}")
    print()
    
    # Example 7: Update packages
    print("Example 7: Update packages")
    print("-" * 60)
    commands = pm.parse("update packages")
    for cmd in commands:
        print(f"  $ {cmd}")
    print()
    
    # Example 8: Search for packages
    print("Example 8: Search for python packages")
    print("-" * 60)
    results = pm.search_packages("python")
    for category, packages in results.items():
        print(f"  {category}: {', '.join(packages)}")
    print()
    
    # Example 9: Get supported software
    print("Example 9: Supported software categories")
    print("-" * 60)
    supported = pm.get_supported_software()
    print(f"  Total categories: {len(supported)}")
    print(f"  Categories: {', '.join(supported[:10])}...")
    print()
    
    # Example 10: Different package managers
    print("Example 10: YUM package manager")
    print("-" * 60)
    pm_yum = PackageManager(package_manager="yum")
    commands = pm_yum.parse("install apache")
    for cmd in commands:
        print(f"  $ {cmd}")
    print()


if __name__ == "__main__":
    main()
