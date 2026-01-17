/**
 * @file common.h
 * @brief Common types and constants for cortexd
 */

#pragma once

#include <chrono>
#include <nlohmann/json.hpp>

namespace cortexd {

// JSON type alias
using json = nlohmann::json;

// Version info - CORTEXD_VERSION is defined by CMake from PROJECT_VERSION
#ifndef CORTEXD_VERSION
#define CORTEXD_VERSION "1.0.0"  // Fallback for non-CMake builds
#endif
constexpr const char* VERSION = CORTEXD_VERSION;
constexpr const char* NAME = "cortexd";

// Socket constants
constexpr const char* DEFAULT_SOCKET_PATH = "/run/cortex/cortex.sock";
constexpr int SOCKET_BACKLOG = 16;
constexpr int SOCKET_TIMEOUT_MS = 5000;
constexpr size_t MAX_MESSAGE_SIZE = 65536;  // 64KB

// Performance targets
constexpr int STARTUP_TIME_MS = 1000;  // Target: < 1 second startup time

// Clock type alias for consistency (used in IPC protocol)
using Clock = std::chrono::system_clock;

} // namespace cortexd
