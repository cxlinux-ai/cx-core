import os

from setuptools import find_packages, setup

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
    requirements = ["anthropic>=0.18.0", "openai>=1.0.0"]

setup(
    name="cortex-linux",
    version="0.1.0",
    author="Cortex Linux",
    author_email="mike@cortexlinux.com",
    description="AI-powered Linux command interpreter",
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
        ],
    },
    include_package_data=True,
)
