/**
 * @file common.h
 * @brief Common types, constants, and utilities for cortexd
 */

#pragma once

#include <string>
#include <chrono>
#include <cstdint>
#include <nlohmann/json.hpp>

namespace cortexd {

using json = nlohmann::json;
using Clock = std::chrono::system_clock;
using TimePoint = std::chrono::system_clock::time_point;
using Duration = std::chrono::milliseconds;

// Version information
constexpr const char* VERSION = "1.0.0";
constexpr const char* NAME = "cortexd";

// Default paths
constexpr const char* DEFAULT_SOCKET_PATH = "/run/cortex/cortex.sock";
constexpr const char* DEFAULT_CONFIG_PATH = "/etc/cortex/daemon.yaml";
constexpr const char* DEFAULT_STATE_DIR = "/var/lib/cortex";
constexpr const char* DEFAULT_ALERT_DB = "~/.cortex/alerts.db";

// Socket configuration
constexpr int SOCKET_BACKLOG = 16;
constexpr int SOCKET_TIMEOUT_MS = 5000;
constexpr size_t MAX_MESSAGE_SIZE = 65536;

// Memory constraints (MB)
constexpr size_t IDLE_MEMORY_MB = 50;
constexpr size_t ACTIVE_MEMORY_MB = 150;

// Performance targets (ms)
constexpr int TARGET_STARTUP_MS = 1000;
constexpr int TARGET_SOCKET_LATENCY_MS = 50;
constexpr int TARGET_INFERENCE_LATENCY_MS = 100;

// Monitoring defaults
constexpr int DEFAULT_MONITOR_INTERVAL_SEC = 300;  // 5 minutes
constexpr double DEFAULT_DISK_WARN_THRESHOLD = 0.80;
constexpr double DEFAULT_DISK_CRIT_THRESHOLD = 0.95;
constexpr double DEFAULT_MEM_WARN_THRESHOLD = 0.85;
constexpr double DEFAULT_MEM_CRIT_THRESHOLD = 0.95;

// Alert retention
constexpr int ALERT_RETENTION_HOURS = 168;  // 7 days

// Rate limiting
constexpr int MAX_REQUESTS_PER_SECOND = 100;
constexpr size_t MAX_INFERENCE_QUEUE_SIZE = 100;
constexpr size_t MAX_PROMPT_SIZE = 8192;

/**
 * @brief Alert severity levels
 */
enum class AlertSeverity {
    INFO = 0,
    WARNING = 1,
    ERROR = 2,
    CRITICAL = 3
};

/**
 * @brief Alert types for categorization
 */
enum class AlertType {
    SYSTEM,           // General system alerts
    APT_UPDATES,      // Package updates available
    SECURITY_UPDATE,  // Security updates available
    DISK_USAGE,       // Disk space alerts
    MEMORY_USAGE,     // Memory usage alerts
    CVE_FOUND,        // Vulnerability detected
    DEPENDENCY,       // Dependency conflict
    LLM_ERROR,        // LLM-related errors
    DAEMON_STATUS,    // Daemon status changes
    AI_ANALYSIS       // AI-generated analysis alert
};

// Convert enums to strings
inline const char* to_string(AlertSeverity severity) {
    switch (severity) {
        case AlertSeverity::INFO: return "info";
        case AlertSeverity::WARNING: return "warning";
        case AlertSeverity::ERROR: return "error";
        case AlertSeverity::CRITICAL: return "critical";
        default: return "unknown";
    }
}

inline const char* to_string(AlertType type) {
    switch (type) {
        case AlertType::SYSTEM: return "system";
        case AlertType::APT_UPDATES: return "apt_updates";
        case AlertType::SECURITY_UPDATE: return "security_update";
        case AlertType::DISK_USAGE: return "disk_usage";
        case AlertType::MEMORY_USAGE: return "memory_usage";
        case AlertType::CVE_FOUND: return "cve_found";
        case AlertType::DEPENDENCY: return "dependency";
        case AlertType::LLM_ERROR: return "llm_error";
        case AlertType::DAEMON_STATUS: return "daemon_status";
        case AlertType::AI_ANALYSIS: return "ai_analysis";
        default: return "unknown";
    }
}

inline AlertSeverity severity_from_string(const std::string& s) {
    if (s == "info") return AlertSeverity::INFO;
    if (s == "warning") return AlertSeverity::WARNING;
    if (s == "error") return AlertSeverity::ERROR;
    if (s == "critical") return AlertSeverity::CRITICAL;
    return AlertSeverity::INFO;
}

inline AlertType alert_type_from_string(const std::string& s) {
    if (s == "system") return AlertType::SYSTEM;
    if (s == "apt_updates") return AlertType::APT_UPDATES;
    if (s == "security_update") return AlertType::SECURITY_UPDATE;
    if (s == "disk_usage") return AlertType::DISK_USAGE;
    if (s == "memory_usage") return AlertType::MEMORY_USAGE;
    if (s == "cve_found") return AlertType::CVE_FOUND;
    if (s == "dependency") return AlertType::DEPENDENCY;
    if (s == "llm_error") return AlertType::LLM_ERROR;
    if (s == "daemon_status") return AlertType::DAEMON_STATUS;
    if (s == "ai_analysis") return AlertType::AI_ANALYSIS;
    return AlertType::SYSTEM;
}

/**
 * @brief Expand ~ to home directory in paths
 */
inline std::string expand_path(const std::string& path) {
    if (path.empty() || path[0] != '~') {
        return path;
    }
    const char* home = std::getenv("HOME");
    if (!home) {
        return path;
    }
    return std::string(home) + path.substr(1);
}

/**
 * @brief Get current timestamp in ISO format (thread-safe)
 */
inline std::string timestamp_iso() {
    auto now = Clock::now();
    auto time_t_now = Clock::to_time_t(now);
    std::tm tm{};
    if (gmtime_r(&time_t_now, &tm) == nullptr) {
        return "";  // gmtime_r failed (unlikely)
    }
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return buf;
}

/**
 * @brief Health snapshot - current system state
 */
struct HealthSnapshot {
    TimePoint timestamp;
    
    // Resource usage
    double cpu_usage_percent = 0.0;
    double memory_usage_percent = 0.0;
    double memory_used_mb = 0.0;
    double memory_total_mb = 0.0;
    double disk_usage_percent = 0.0;
    double disk_used_gb = 0.0;
    double disk_total_gb = 0.0;
    
    // Package state
    int pending_updates = 0;
    int security_updates = 0;
    
    // Alerts
    int active_alerts = 0;
    int critical_alerts = 0;
    
    json to_json() const {
        return {
            {"timestamp", Clock::to_time_t(timestamp)},
            {"cpu_usage_percent", cpu_usage_percent},
            {"memory_usage_percent", memory_usage_percent},
            {"memory_used_mb", memory_used_mb},
            {"memory_total_mb", memory_total_mb},
            {"disk_usage_percent", disk_usage_percent},
            {"disk_used_gb", disk_used_gb},
            {"disk_total_gb", disk_total_gb},
            {"pending_updates", pending_updates},
            {"security_updates", security_updates},
            {"active_alerts", active_alerts},
            {"critical_alerts", critical_alerts}
        };
    }
};

} // namespace cortexd

