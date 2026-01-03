# Building Packages from Source

Cortex Linux supports building and installing packages from source code when pre-built binaries are unavailable or when you need a specific version or configuration.

## Overview

The source build feature allows you to:
- Download source code from various sources (GitHub, tarballs, etc.)
- Automatically detect build dependencies
- Configure build options
- Compile and build packages
- Install built packages
- Cache build artifacts for reuse

## Usage

### Basic Usage

Build a package from source:

```bash
cortex install python@3.12 --from-source
```

### With Source URL

Specify a custom source URL:

```bash
cortex install mypackage --from-source --source-url https://example.com/mypackage.tar.gz
```

### With Version

Specify a version to build:

```bash
cortex install python --from-source --version 3.12.0
```

### Dry Run

Preview build commands without executing:

```bash
cortex install python@3.12 --from-source --dry-run
```

### Execute Build

Build and install:

```bash
cortex install python@3.12 --from-source --execute
```

## Supported Build Systems

Cortex automatically detects and supports the following build systems:

### Autotools (GNU Build System)
- Detected by presence of `configure` script or `configure.ac`
- Uses `./configure` for configuration
- Uses `make` for building
- Uses `sudo make install` for installation

### CMake
- Detected by presence of `CMakeLists.txt`
- Uses `cmake` for configuration
- Uses `make` for building
- Uses `sudo make install` for installation

### Make
- Detected by presence of `Makefile`
- Uses `make` directly for building
- Uses `sudo make install` for installation

### Python
- Detected by presence of `setup.py` or `pyproject.toml`
- Uses `python3 setup.py build` for building
- Uses `sudo python3 setup.py install` for installation

## Build Dependencies

Cortex automatically detects and installs required build dependencies:

### Base Dependencies
- `build-essential` - Essential build tools
- `gcc`, `g++` - Compilers
- `make` - Build automation
- `cmake` - CMake build system
- `pkg-config` - Package configuration

### Autotools Dependencies
- `autoconf` - Generate configuration scripts
- `automake` - Generate Makefiles
- `libtool` - Library building support
- `gettext` - Internationalization

### Python Dependencies
- `python3-dev` - Python development headers
- `python3-pip` - Python package installer
- `python3-setuptools` - Python packaging tools
- `python3-wheel` - Python wheel format support

### Common Library Dependencies
- `libssl-dev` - SSL/TLS development libraries
- `zlib1g-dev` - Compression library
- `libcurl4-openssl-dev` - HTTP client library
- `libxml2-dev` - XML parsing library
- `libsqlite3-dev` - SQLite database library
- `libreadline-dev` - Command line editing library

## Build Configuration

### Default Configuration

By default, Cortex uses:
- Installation prefix: `/usr/local`
- Build optimizations enabled
- Parallel builds (using all CPU cores)

### Custom Configuration

You can customize build options by modifying the source code or using environment variables. For advanced configuration, you may need to manually edit the build scripts.

## Build Caching

Cortex caches build artifacts to speed up subsequent builds:

- Cache location: `~/.cortex/build_cache/`
- Cache key: Based on package name, version, and source URL
- Cache includes: Build metadata and install commands

### Cache Benefits

- Faster rebuilds when source hasn't changed
- Reduced network usage
- Consistent builds across sessions

### Clearing Cache

To clear the build cache:

```bash
rm -rf ~/.cortex/build_cache/
```

## Example: Building Python from Source

```bash
# Download and build Python 3.12.0
cortex install python@3.12.0 --from-source --execute

# The process will:
# 1. Download Python 3.12.0 source
# 2. Check for build dependencies (gcc, make, libssl-dev, etc.)
# 3. Install missing dependencies
# 4. Configure the build with optimizations
# 5. Compile Python (may take 10-15 minutes)
# 6. Install to /usr/local
```

## Example: Building Custom Package

```bash
# Build from GitHub release
cortex install myapp \
  --from-source \
  --source-url https://github.com/user/myapp/archive/refs/tags/v1.0.0.tar.gz \
  --execute
```

## Troubleshooting

### Build Fails with Missing Dependencies

If build fails due to missing dependencies:

1. Check the error message for the missing package
2. Install it manually: `sudo apt-get install <package>`
3. Retry the build

### Build Takes Too Long

- Large packages (like Python) can take 10-30 minutes to compile
- Use `--dry-run` first to preview the build
- Consider using pre-built binaries if available

### Permission Errors

- Build requires `sudo` for installation
- Ensure you have sudo privileges
- Check that `/usr/local` is writable

### Source Download Fails

- Verify the source URL is accessible
- Check network connectivity
- Try downloading manually to verify URL

### Build System Not Detected

If Cortex can't detect the build system:

1. Check that standard build files exist (`configure`, `CMakeLists.txt`, `Makefile`, etc.)
2. Manually specify build system (future feature)
3. Use manual build process if needed

## Best Practices

1. **Always use `--dry-run` first** to preview what will happen
2. **Check build dependencies** before starting long builds
3. **Use version pinning** (`@version`) for reproducible builds
4. **Cache builds** when rebuilding the same version
5. **Monitor disk space** - builds can use significant space
6. **Use `--execute`** only when ready to install

## Limitations

- Currently supports common build systems (autotools, cmake, make, python)
- Source URL detection is limited to common patterns
- Some packages may require manual configuration
- Build time can be significant for large packages
- Requires build dependencies to be available in repositories

## Future Enhancements

Planned improvements:
- Support for more build systems (meson, cargo, etc.)
- Automatic source URL detection from package names
- Custom build script support
- Build option presets
- Parallel package builds
- Build verification and testing

## See Also

- [Installation Guide](Getting-Started.md)
- [Dependency Resolution](README_DEPENDENCIES.md)
- [CLI Reference](COMMANDS.md)

