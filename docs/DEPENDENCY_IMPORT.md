# Dependency Import

Import and install packages from dependency files across multiple ecosystems.

## Overview

The `cortex import` command parses dependency files from various package managers and installs the packages. It supports:

- **Python**: `requirements.txt`
- **Node.js**: `package.json`
- **Ruby**: `Gemfile`
- **Rust**: `Cargo.toml`
- **Go**: `go.mod`

## Usage

### Basic Usage

```bash
# Parse and show packages (dry-run by default)
cortex import requirements.txt

# Actually install packages
cortex import requirements.txt --execute

# Include dev dependencies
cortex import package.json --dev

# Scan directory for all dependency files
cortex import --all

# Scan and install all
cortex import --all --execute
```

### Command Options

| Option | Short | Description |
|--------|-------|-------------|
| `--execute` | `-e` | Execute install commands (default: dry-run) |
| `--dev` | `-d` | Include dev dependencies |
| `--all` | `-a` | Scan directory for all dependency files |

## Supported Formats

### Python (requirements.txt)

Parses standard pip requirements format:

```txt
# Comments are ignored
requests==2.28.0
flask>=2.0.0
django~=4.0
numpy<2.0,>=1.5

# Extras
requests[security,socks]

# Git URLs
git+https://github.com/user/repo.git#egg=mypackage

# Editable installs
-e ./local_package

# Include other files
-r base-requirements.txt
```

**Features:**
- Version specifiers (`==`, `>=`, `<=`, `~=`, `!=`, `<`, `>`)
- Extras (`package[extra1,extra2]`)
- Environment markers (`package; python_version >= "3.8"`)
- Recursive includes (`-r other-file.txt`)
- Git URLs and editable installs
- Comments and blank lines

**Install Command:** `pip install -r <file>`

### Node.js (package.json)

Parses npm/yarn package files:

```json
{
  "dependencies": {
    "express": "^4.18.0",
    "@types/node": "^18.0.0"
  },
  "devDependencies": {
    "jest": "^29.0.0",
    "typescript": "^5.0.0"
  },
  "optionalDependencies": {
    "fsevents": "^2.3.0"
  }
}
```

**Features:**
- Production dependencies
- Dev dependencies (with `--dev` flag)
- Optional dependencies
- Scoped packages (`@scope/package`)
- Version ranges (`^`, `~`, `>=`, `*`, `latest`)
- Git URLs and local paths
- Peer dependencies (shown as warning)

**Install Command:** `npm install`

### Ruby (Gemfile)

Parses Bundler Gemfiles:

```ruby
source 'https://rubygems.org'

ruby '3.2.0'

gem 'rails', '~> 7.0'
gem 'pg', '>= 1.0'

group :development, :test do
  gem 'rspec'
  gem 'factory_bot'
end

gem 'rubocop', group: :development
gem 'local_gem', path: './gems/local'
gem 'git_gem', git: 'https://github.com/user/repo.git'
```

**Features:**
- Gem declarations with versions
- Groups (`:development`, `:test`, `:production`)
- Inline group syntax
- Path-based gems
- Git-based gems
- Source declarations
- Ruby version requirements (ignored)

**Install Command:** `bundle install`

### Rust (Cargo.toml)

Parses Cargo manifest files:

```toml
[package]
name = "my_project"
version = "0.1.0"

[dependencies]
serde = "1.0"
tokio = { version = "1.0", features = ["full"] }
local_crate = { path = "../local" }
git_crate = { git = "https://github.com/user/repo.git" }

[dev-dependencies]
criterion = "0.4"

[build-dependencies]
cc = "1.0"
```

**Features:**
- Simple version strings
- Inline tables with version and features
- Path dependencies
- Git dependencies
- Optional dependencies
- Dev dependencies (with `--dev` flag)
- Build dependencies (treated as dev)

**Install Command:** `cargo build`

### Go (go.mod)

Parses Go module files:

```go
module example.com/mymodule

go 1.21

require (
    github.com/gin-gonic/gin v1.9.0
    github.com/go-redis/redis/v8 v8.11.5
    golang.org/x/sync v0.0.0-20220722155255-886fb9371eb4
)

require (
    github.com/indirect/dep v1.0.0 // indirect
)

replace github.com/old => github.com/new v1.0.0
```

**Features:**
- Single and block require statements
- Indirect dependencies (marked with `// indirect`)
- Pseudo-versions (commit hashes)
- Replace directives (shown as warning)
- Exclude directives (shown as warning)

**Install Command:** `go mod download`

## Examples

### Single File Import

```bash
$ cortex import requirements.txt

📋 Found 25 Python packages

Packages:
  • requests (==2.28.0)
  • flask (>=2.0.0)
  • django (~=4.0)
  ... and 22 more

Install command: pip install -r requirements.txt

To install these packages, run with --execute flag
Example: cortex import requirements.txt --execute
```

### With Dev Dependencies

```bash
$ cortex import package.json --dev

📋 Found 12 Node packages

Packages:
  • express (^4.18.0)
  • lodash (~4.17.21)
  ... and 3 more

Dev packages: (7)
  • jest (^29.0.0)
  • typescript (^5.0.0)
  ... and 5 more

Install command: npm install

To install these packages, run with --execute flag
Example: cortex import package.json --execute
```

### Scan All Dependencies

```bash
$ cortex import --all
Scanning directory...
   ✓  requirements.txt (25 packages)
   ✓  package.json (42 packages)
   ✓  Gemfile (8 packages)

Install commands:
  • pip install -r requirements.txt
  • npm install
  • bundle install

To install all packages, run with --execute flag
Example: cortex import --all --execute
```

### Execute Installation

```bash
$ cortex import --all --execute
Scanning directory...
   ✓  requirements.txt (25 packages)
   ✓  package.json (42 packages)

Install all 67 packages? [Y/n]: y

Installing packages...

[1/2] ✅ Install Python packages from requirements.txt
  Command: pip install -r requirements.txt

[2/2] ✅ Install Node packages
  Command: npm install

All packages installed successfully!
Completed in 45.32 seconds
```

## Error Handling

### File Not Found

```bash
$ cortex import nonexistent.txt
Error: File not found: nonexistent.txt
```

### Invalid JSON

```bash
$ cortex import package.json
Error: Invalid JSON: Expecting property name enclosed in double quotes
```

### Unknown File Type

```bash
$ cortex import unknown.xyz
Error: Unknown file type: unknown.xyz
```

## Programmatic Usage

The `DependencyImporter` class can be used programmatically:

```python
from cortex.dependency_importer import DependencyImporter, PackageEcosystem

# Create importer
importer = DependencyImporter()

# Parse a single file
result = importer.parse("requirements.txt", include_dev=True)

print(f"Found {result.prod_count} packages")
for pkg in result.packages:
    print(f"  - {pkg.name} ({pkg.version})")

# Scan directory
results = importer.scan_directory(include_dev=True)
for file_path, result in results.items():
    print(f"{file_path}: {result.total_count} packages")

# Get install commands
commands = importer.get_install_commands_for_results(results)
for cmd in commands:
    print(f"  {cmd['command']}")
```

## Dev Dependencies

By default, dev dependencies are **not** included. Use the `--dev` flag to include them:

| Ecosystem | Dev Dependencies |
|-----------|-----------------|
| Python | Files named `*dev*`, `*test*` in filename |
| Node.js | `devDependencies` in package.json |
| Ruby | Groups `:development`, `:test` |
| Rust | `[dev-dependencies]`, `[build-dependencies]` |
| Go | N/A (go.mod doesn't distinguish) |

## Confirmation Prompt

When using `--execute` with `--all`, you'll be prompted for confirmation:

```
Install all 67 packages? [Y/n]:
```

This prevents accidental mass installations. Single file imports with `--execute` do not require confirmation.

## Limitations

- **No lock file support**: Uses main dependency files only (not `package-lock.json`, `Gemfile.lock`, etc.)
- **No version resolution**: Installs versions as specified in the files
- **No conflict detection**: Doesn't check for version conflicts between ecosystems
- **Network required**: Package installation requires network access

## Related Commands

- `cortex install <package>` - Install a single package with AI assistance
- `cortex stack <name>` - Install predefined package stacks
- `cortex history` - View installation history
- `cortex rollback <id>` - Undo an installation
