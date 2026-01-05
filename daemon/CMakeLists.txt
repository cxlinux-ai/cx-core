cmake_minimum_required(VERSION 3.20)
project(cortexd VERSION 0.1.0 LANGUAGES CXX)

# Set CMake policy for FetchContent timestamp handling
cmake_policy(SET CMP0135 NEW)

# Set C++ standard to C++17
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)

# Build type defaults to Release
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler flags for optimization and warnings
if(MSVC)
    add_compile_options(/W4 /WX)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
    # Suppress linker warnings about static glibc functions in systemd (harmless - daemon works fine)
    string(APPEND CMAKE_EXE_LINKER_FLAGS " -Wl,--no-warnings")
    if(CMAKE_BUILD_TYPE STREQUAL "Release")
        add_compile_options(-O3)
    endif()
endif()

# Find required packages
find_package(systemd QUIET)
find_package(PkgConfig REQUIRED)
pkg_check_modules(OPENSSL REQUIRED openssl)
pkg_check_modules(SQLITE3 REQUIRED sqlite3)
pkg_check_modules(SYSTEMD libsystemd QUIET)

# Find llama.cpp - check multiple possible locations
find_package(llama QUIET)
if(NOT llama_FOUND)
    # Try pkg-config
    pkg_check_modules(LLAMA llama QUIET)
endif()

# If llama.cpp not found, provide helpful message
if(NOT llama_FOUND AND NOT LLAMA_FOUND)
    message(STATUS "llama.cpp not found. Install with: apt-get install libllama-dev")
    message(STATUS "Or clone from: https://github.com/ggerganov/llama.cpp")
endif()

# Include directories
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)
include_directories(${OPENSSL_INCLUDE_DIRS})
include_directories(${SQLITE3_INCLUDE_DIRS})
if(LLAMA_INCLUDE_DIRS)
    include_directories(${LLAMA_INCLUDE_DIRS})
endif()
if(llama_INCLUDE_DIRS)
    include_directories(${llama_INCLUDE_DIRS})
endif()

# Source files
set(DAEMON_SOURCES
    src/main.cpp
    src/server/socket_server.cpp
    src/server/ipc_protocol.cpp
    src/monitor/system_monitor.cpp
    src/monitor/apt_monitor.cpp
    src/monitor/disk_monitor.cpp
    src/monitor/memory_monitor.cpp
    src/monitor/cve_scanner.cpp
    src/monitor/dependency_checker.cpp
    src/llm/llama_wrapper.cpp
    src/llm/inference_queue.cpp
    src/config/daemon_config.cpp
    src/alerts/alert_manager.cpp
    src/alerts/alert_store.cpp
    src/utils/logging.cpp
    src/utils/util_functions.cpp
)

# Main daemon executable
add_executable(cortexd ${DAEMON_SOURCES})

# Link libraries
target_link_libraries(cortexd
    PRIVATE
    ${OPENSSL_LIBRARIES}
    ${SQLITE3_LIBRARIES}
    ${SYSTEMD_LIBRARIES}
    ${LLAMA_LIBRARIES}
    ${llama_LIBRARIES}
    cap
    uuid
    pthread
    pthread
)

# Link llama.cpp if available (force dynamic linking for llama)
if(llama_LIBRARY)
    target_link_libraries(cortexd PRIVATE ${llama_LIBRARY})
    message(STATUS "Linked llama.cpp library: ${llama_LIBRARY}")
elseif(LLAMA_LIBRARIES)
    target_link_libraries(cortexd PRIVATE ${LLAMA_LIBRARIES})
elseif(llama_LIBRARIES)
    target_link_libraries(cortexd PRIVATE ${llama_LIBRARIES})
else()
    # Try linking directly to libllama.so if it exists
    if(EXISTS "/usr/local/lib/libllama.so")
        target_link_libraries(cortexd PRIVATE /usr/local/lib/libllama.so)
        message(STATUS "Linked llama.cpp library: /usr/local/lib/libllama.so")
    endif()
endif()

# Build as position-independent executable for better security
set_target_properties(cortexd PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)
if(NOT APPLE)
# Note: Removed -static flag to allow dynamic linking with libllama.so
# target_link_options(cortexd PRIVATE -static)
endif()

# Installation
install(TARGETS cortexd
    RUNTIME DESTINATION /usr/local/bin
)

install(FILES daemon/cortexd.service
    DESTINATION /etc/systemd/system/
)

install(FILES daemon/cortexd.default
    DESTINATION /etc/default/
    RENAME cortexd
)

# Print build info
message(STATUS "Building cortexd version ${PROJECT_VERSION}")
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "C++ Standard: ${CMAKE_CXX_STANDARD}")
