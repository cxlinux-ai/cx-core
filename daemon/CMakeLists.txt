cmake_minimum_required(VERSION 3.20)
project(cortexd VERSION 1.0.0 LANGUAGES CXX)

# CMake policies
cmake_policy(SET CMP0135 NEW)

# Require C++17
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build options
option(BUILD_TESTS "Build test suite" OFF)
option(BUILD_STATIC "Build static binary" OFF)
option(ENABLE_SANITIZERS "Enable address/undefined sanitizers" OFF)

# Build type defaults to Release
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler flags
add_compile_options(-Wall -Wextra -Wpedantic)

if(CMAKE_BUILD_TYPE STREQUAL "Release")
    add_compile_options(-O3 -DNDEBUG)
endif()

if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    add_compile_options(-g3 -O0)
endif()

if(ENABLE_SANITIZERS)
    add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
    add_link_options(-fsanitize=address,undefined)
endif()

# Linker warnings documentation
# ============================
# We do NOT suppress linker warnings to ensure we catch genuine issues.
# However, some warnings from third-party libraries are expected and can be ignored:
#
# WARNINGS TO IGNORE (harmless, from third-party libraries):
# - Symbol versioning warnings from systemd/OpenSSL (e.g., "version node not found")
#   These are due to library ABI versioning and don't affect functionality.
# - Deprecated symbol warnings from older library versions
#   These are library-internal and don't affect our code.
#
# WARNINGS TO TAKE SERIOUSLY (indicate real problems):
# - "undefined reference to ..." - Missing library or incorrect linking
# - "multiple definition of ..." - Duplicate symbol definitions
# - "cannot find -l..." - Missing library dependency
# - "relocation R_X86_64_PC32 against symbol ... can not be used" - PIC issues
# - Any warnings about our own code (src/*.cpp, include/cortexd/*.h)
#
# If you see linker warnings, check:
# 1. Are they from third-party libraries (systemd, OpenSSL, etc.)? → Usually safe to ignore
# 2. Are they about undefined symbols in our code? → MUST FIX
# 3. Do they prevent the build from completing? → MUST FIX
# 4. Do tests pass? → If yes, likely harmless third-party noise

# Find required packages
find_package(PkgConfig REQUIRED)
pkg_check_modules(SYSTEMD REQUIRED libsystemd)
pkg_check_modules(OPENSSL REQUIRED openssl)
pkg_check_modules(UUID REQUIRED uuid)

# Fetch nlohmann/json
include(FetchContent)
FetchContent_Declare(json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
    GIT_SHALLOW TRUE
)
FetchContent_MakeAvailable(json)

# Fetch yaml-cpp
# Note: yaml-cpp 0.8.0 already has cmake_minimum_required(VERSION 3.5), no patching needed
FetchContent_Declare(yaml-cpp
    GIT_REPOSITORY https://github.com/jbeder/yaml-cpp.git
    GIT_TAG 0.8.0
    GIT_SHALLOW TRUE
)
set(YAML_CPP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(YAML_CPP_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(yaml-cpp)

# Include directories
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${SYSTEMD_INCLUDE_DIRS}
    ${OPENSSL_INCLUDE_DIRS}
    ${UUID_INCLUDE_DIRS}
)

# Source files
set(DAEMON_SOURCES
    # Core
    src/main.cpp
    src/core/daemon.cpp
    
    # Config
    src/config/config.cpp
    
    # IPC
    src/ipc/server.cpp
    src/ipc/protocol.cpp
    src/ipc/handlers.cpp
    
    # Utils
    src/utils/logger.cpp
)

# Main daemon executable
add_executable(cortexd ${DAEMON_SOURCES})

# Compile definitions
target_compile_definitions(cortexd PRIVATE
    CORTEXD_VERSION="${PROJECT_VERSION}"
)

# Link libraries
target_link_libraries(cortexd
    PRIVATE
    ${SYSTEMD_LIBRARIES}
    ${OPENSSL_LIBRARIES}
    ${UUID_LIBRARIES}
    nlohmann_json::nlohmann_json
    yaml-cpp::yaml-cpp
    pthread
)

# Static build option
# Use partial static linking to allow libsystemd to use dlopen
if(BUILD_STATIC)
    target_link_options(cortexd PRIVATE -static-libgcc -static-libstdc++)
endif()

# Position independent code
set_target_properties(cortexd PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)

# Installation
install(TARGETS cortexd
    RUNTIME DESTINATION bin
)

install(FILES
    systemd/cortexd.service
    DESTINATION lib/systemd/system
)

install(FILES
    config/cortexd.yaml.example
    DESTINATION share/cortex
)

# Print build summary
message(STATUS "")
message(STATUS "=== cortexd ${PROJECT_VERSION} build configuration ===")
message(STATUS "Build type:     ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ Standard:   ${CMAKE_CXX_STANDARD}")
message(STATUS "Static build:   ${BUILD_STATIC}")
message(STATUS "Tests:          ${BUILD_TESTS}")
message(STATUS "Sanitizers:     ${ENABLE_SANITIZERS}")
message(STATUS "")

# Tests (optional)
if(BUILD_TESTS)
    enable_testing()
    
    # Fetch Google Test
    FetchContent_Declare(googletest
        GIT_REPOSITORY https://github.com/google/googletest.git
        GIT_TAG v1.14.0
        GIT_SHALLOW TRUE
    )
    FetchContent_MakeAvailable(googletest)
    
    add_subdirectory(tests)
endif()
