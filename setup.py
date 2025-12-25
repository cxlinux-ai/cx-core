import os
import sys

from setuptools import find_packages, setup
from setuptools.command.develop import develop
from setuptools.command.egg_info import egg_info
from setuptools.command.install import install


class PostInstallCommand(install):
    """Post-installation setup for Ollama."""

    def run(self):
        install.run(self)
        # Run Ollama setup after installation
        print("\n" + "=" * 70)
        print("🚀 Running Cortex post-installation setup...")
        print("=" * 70 + "\n")
        try:
            # Import and run the setup function directly
            from scripts.setup_ollama import setup_ollama

            setup_ollama()
        except Exception as e:
            print(f"⚠️  Ollama setup encountered an issue: {e}")
            print("ℹ️  You can run it manually later with: cortex-setup-ollama")
        finally:
            print("\n" + "=" * 70)
            print("💡 TIP: If Ollama setup didn't run, execute: cortex-setup-ollama")
            print("=" * 70)


class PostDevelopCommand(develop):
    """Post-development setup for Ollama."""

    def run(self):
        develop.run(self)
        # Run Ollama setup after development install
        print("\n" + "=" * 70)
        print("🚀 Running Cortex post-installation setup...")
        print("=" * 70 + "\n")
        try:
            # Import and run the setup function directly
            from scripts.setup_ollama import setup_ollama

            setup_ollama()
        except Exception as e:
            print(f"⚠️  Ollama setup encountered an issue: {e}")
            print("ℹ️  You can run it manually later with: cortex-setup-ollama")
        finally:
            print("\n" + "=" * 70)
            print("💡 TIP: If Ollama setup didn't run, execute: cortex-setup-ollama")
            print("=" * 70)


class PostEggInfoCommand(egg_info):
    """Post-egg-info setup for Ollama - runs during pip install -e ."""

    def run(self):
        egg_info.run(self)

        # Only run setup once per user
        marker_file = os.path.expanduser("~/.cortex/.setup_done")

        # Skip if in CI or if marker exists (already ran)
        if os.getenv("CI") or os.getenv("GITHUB_ACTIONS") or os.path.exists(marker_file):
            return

        # Skip if not a TTY (can't prompt user)
        if not sys.stdin.isatty():
            sys.stderr.write(
                "\n⚠️  Skipping interactive setup (not a TTY). Run 'cortex-setup-ollama' manually.\n"
            )
            sys.stderr.flush()
            return

        # Run Ollama setup after egg_info - flush output to ensure it's visible
        sys.stdout.write("\n" + "=" * 70 + "\n")
        sys.stdout.write("🚀 Running Cortex post-installation setup...\n")
        sys.stdout.write("=" * 70 + "\n\n")
        sys.stdout.flush()

        try:
            # Import and run the setup function directly
            from scripts.setup_ollama import setup_ollama

            setup_ollama()
            # Create marker file to prevent running again
            os.makedirs(os.path.dirname(marker_file), exist_ok=True)
            with open(marker_file, "w") as f:
                f.write("Setup completed\n")
            sys.stdout.write("\n" + "=" * 70 + "\n")
            sys.stdout.write(
                "✅ Setup complete! You can re-run setup anytime with: cortex-setup-ollama\n"
            )
            sys.stdout.write("=" * 70 + "\n\n")
            sys.stdout.flush()
        except KeyboardInterrupt:
            sys.stdout.write("\n\n⚠️  Setup cancelled by user\n")
            sys.stdout.write("ℹ️  You can run it manually later with: cortex-setup-ollama\n\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"\n⚠️  Ollama setup encountered an issue: {e}\n")
            sys.stderr.write("ℹ️  You can run it manually later with: cortex-setup-ollama\n\n")
            sys.stderr.flush()


with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

# Try to read requirements from root, fallback to LLM directory
requirements_path = "requirements.txt"
if not os.path.exists(requirements_path):
    requirements_path = os.path.join("LLM", "requirements.txt")

if os.path.exists(requirements_path):
    with open(requirements_path, encoding="utf-8") as fh:
        requirements = [
            line.strip()
            for line in fh
            if line.strip() and not line.startswith("#") and not line.startswith("-r")
        ]
else:
    requirements = ["anthropic>=0.18.0", "openai>=1.0.0", "requests>=2.32.4"]

setup(
    name="cortex-linux",
    version="0.1.0",
    author="Cortex Linux",
    author_email="mike@cortexlinux.com",
    description="AI-powered Linux command interpreter with local LLM support",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/cortexlinux/cortex",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Installation/Setup",
        "Topic :: System :: Systems Administration",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "cortex=cortex.cli:main",
            "cortex-setup-ollama=scripts.setup_ollama:setup_ollama",
        ],
    },
    cmdclass={
        "install": PostInstallCommand,
        "develop": PostDevelopCommand,
        "egg_info": PostEggInfoCommand,
    },
    include_package_data=True,
)
