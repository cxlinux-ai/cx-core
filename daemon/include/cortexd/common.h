/**
 * @file common.h
 * @brief Common types and constants for cortexd
 */

#pragma once

#include <string>
#include <vector>
#include <memory>
#include <map>
#include <chrono>
#include <iostream>
#include <sstream>
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

// Memory constraints (in MB)
constexpr int IDLE_MEMORY_MB = 50;
constexpr int ACTIVE_MEMORY_MB = 150;

// Performance targets
constexpr int STARTUP_TIME_MS = 1000;
constexpr int CACHED_INFERENCE_MS = 100;

// Monitoring intervals
constexpr int MONITORING_INTERVAL_SECONDS = 300; // 5 minutes
constexpr int ALERT_RETENTION_DAYS = 7;

// Thresholds
constexpr double DISK_USAGE_THRESHOLD = 0.80;    // 80%
constexpr double MEMORY_USAGE_THRESHOLD = 0.85;  // 85%

// Alert severity levels
enum class AlertSeverity {
    INFO,
    WARNING,
    ERROR,
    CRITICAL
};

// Alert types
enum class AlertType {
    APT_UPDATES,
    DISK_USAGE,
    MEMORY_USAGE,
    CVE_FOUND,
    DEPENDENCY_CONFLICT,
    SYSTEM_ERROR,
    DAEMON_STATUS
};

// IPC command types
enum class CommandType {
    STATUS,
    ALERTS,
    SHUTDOWN,
    CONFIG_RELOAD,
    HEALTH,
    UNKNOWN
};

// Helper functions
std::string to_string(AlertSeverity severity);
std::string to_string(AlertType type);
AlertSeverity severity_from_string(const std::string& s);
AlertType alert_type_from_string(const std::string& s);
CommandType command_from_string(const std::string& cmd);

// Struct for system health snapshot
struct HealthSnapshot {
    std::chrono::system_clock::time_point timestamp;
    double cpu_usage;
    double memory_usage;
    double disk_usage;
    int active_processes;
    int open_files;
    bool llm_loaded;
    int inference_queue_size;
    int alerts_count;
};

// Clock type alias for consistency
using Clock = std::chrono::system_clock;

} // namespace cortexd
