#include "cortexd_common.h"
#include <algorithm>
#include <uuid/uuid.h>

namespace cortex {
namespace daemon {

std::string to_string(AlertSeverity severity) {
    switch (severity) {
        case AlertSeverity::INFO:
            return "info";
        case AlertSeverity::WARNING:
            return "warning";
        case AlertSeverity::ERROR:
            return "error";
        case AlertSeverity::CRITICAL:
            return "critical";
        default:
            return "unknown";
    }
}

std::string to_string(AlertType type) {
    switch (type) {
        case AlertType::APT_UPDATES:
            return "apt_updates";
        case AlertType::DISK_USAGE:
            return "disk_usage";
        case AlertType::MEMORY_USAGE:
            return "memory_usage";
        case AlertType::CVE_FOUND:
            return "cve_found";
        case AlertType::DEPENDENCY_CONFLICT:
            return "dependency_conflict";
        case AlertType::SYSTEM_ERROR:
            return "system_error";
        case AlertType::DAEMON_STATUS:
            return "daemon_status";
        default:
            return "unknown";
    }
}

AlertSeverity severity_from_string(const std::string& s) {
    std::string lower = s;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

    if (lower == "info") return AlertSeverity::INFO;
    if (lower == "warning") return AlertSeverity::WARNING;
    if (lower == "error") return AlertSeverity::ERROR;
    if (lower == "critical") return AlertSeverity::CRITICAL;
    return AlertSeverity::INFO;
}

AlertType alert_type_from_string(const std::string& s) {
    std::string lower = s;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

    if (lower == "apt_updates") return AlertType::APT_UPDATES;
    if (lower == "disk_usage") return AlertType::DISK_USAGE;
    if (lower == "memory_usage") return AlertType::MEMORY_USAGE;
    if (lower == "cve_found") return AlertType::CVE_FOUND;
    if (lower == "dependency_conflict") return AlertType::DEPENDENCY_CONFLICT;
    if (lower == "system_error") return AlertType::SYSTEM_ERROR;
    if (lower == "daemon_status") return AlertType::DAEMON_STATUS;
    return AlertType::SYSTEM_ERROR;
}

CommandType command_from_string(const std::string& cmd) {
    std::string lower = cmd;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);

    if (lower == "status") return CommandType::STATUS;
    if (lower == "alerts") return CommandType::ALERTS;
    if (lower == "shutdown") return CommandType::SHUTDOWN;
    if (lower == "config_reload" || lower == "config-reload") return CommandType::CONFIG_RELOAD;
    if (lower == "health") return CommandType::HEALTH;
    return CommandType::UNKNOWN;
}

} // namespace daemon
} // namespace cortex
