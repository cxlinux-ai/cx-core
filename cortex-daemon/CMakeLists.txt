cmake_minimum_required(VERSION 3.20)
project(cortex-daemon VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 11)

# Build options
option(CORTEX_STATIC_LINK    "Link llama.cpp statically"          ON)
option(CORTEX_METAL           "Enable Apple Metal GPU (macOS)"    OFF)
option(CORTEX_CUDA            "Enable NVIDIA CUDA GPU"            OFF)
option(CORTEX_VULKAN          "Enable Vulkan GPU"                 OFF)
option(CORTEX_AVX2            "Enable AVX2 SIMD (x86_64)"        OFF)

# Detect architecture
if(CMAKE_SYSTEM_PROCESSOR MATCHES "arm64|aarch64")
    set(ARCH_ARM64 TRUE)
    message(STATUS "Target: ARM64")
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|amd64|AMD64")
    set(ARCH_X86_64 TRUE)
    message(STATUS "Target: x86_64")
else()
    message(FATAL_ERROR "Unsupported architecture: ${CMAKE_SYSTEM_PROCESSOR}")
endif()

# ── llama.cpp submodule ──────────────────────────────────────────────────────
set(LLAMA_CPP_DIR "${CMAKE_SOURCE_DIR}/vendor/llama.cpp")

if(NOT EXISTS "${LLAMA_CPP_DIR}/CMakeLists.txt")
    message(FATAL_ERROR
        "llama.cpp submodule not found. Run:\n"
        "  git submodule update --init --recursive")
endif()

# Forward GPU options into llama.cpp's own build
set(LLAMA_METAL  ${CORTEX_METAL}  CACHE BOOL "" FORCE)
set(LLAMA_CUDA   ${CORTEX_CUDA}   CACHE BOOL "" FORCE)
set(LLAMA_VULKAN ${CORTEX_VULKAN} CACHE BOOL "" FORCE)

# Build llama.cpp as a library only (no CLI executables)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS    OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER   OFF CACHE BOOL "" FORCE)

add_subdirectory(${LLAMA_CPP_DIR} llama_cpp_build)

# ── Cortex inference library ─────────────────────────────────────────────────
set(INFERENCE_SOURCES
    src/inference/llama_engine.cpp
    src/inference/inference_manager.cpp
    src/bindings/llama_c_bridge.cpp
    src/models/model_registry.cpp
)

if(CORTEX_STATIC_LINK)
    add_library(cortex_inference STATIC ${INFERENCE_SOURCES})
else()
    add_library(cortex_inference SHARED ${INFERENCE_SOURCES})
    set_target_properties(cortex_inference PROPERTIES
        VERSION   ${PROJECT_VERSION}
        SOVERSION 1
    )
endif()

target_include_directories(cortex_inference
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_SOURCE_DIR}/src>
        $<INSTALL_INTERFACE:include/cortex>
    PRIVATE
        ${LLAMA_CPP_DIR}
        ${LLAMA_CPP_DIR}/common
)

target_link_libraries(cortex_inference
    PUBLIC  llama
    PRIVATE $<$<PLATFORM_ID:Linux>:pthread>
            $<$<PLATFORM_ID:Linux>:dl>
)

# Architecture-specific flags
if(ARCH_ARM64)
    target_compile_options(cortex_inference PRIVATE -march=armv8-a+dotprod+fp16)
elseif(ARCH_X86_64)
    target_compile_options(cortex_inference PRIVATE
        -march=native
        $<$<BOOL:${CORTEX_AVX2}>:-mavx2 -mfma>
    )
endif()

target_compile_options(cortex_inference PRIVATE
    -O3
    -ffast-math
    -fvisibility=hidden
    $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic>
)

# ── Cortex daemon executable ─────────────────────────────────────────────────
add_executable(cortexd src/main.cpp)
target_link_libraries(cortexd PRIVATE cortex_inference)

# ── Tests ────────────────────────────────────────────────────────────────────
enable_testing()
add_subdirectory(tests)
