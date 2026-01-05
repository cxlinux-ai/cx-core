#include "alert_manager.h"
#include "logging.h"
#include <uuid/uuid.h>
#include <mutex>

namespace cortex {
namespace daemon {

json Alert::to_json() const {
    json j;
    j["id"] = id;
    j["timestamp"] = std::chrono::system_clock::to_time_t(timestamp);
    j["severity"] = to_string(severity);
    j["type"] = to_string(type);
    j["title"] = title;
    j["description"] = description;
    j["acknowledged"] = acknowledged;
    j["metadata"] = metadata;
    return j;
}

Alert Alert::from_json(const json& j) {
    Alert alert;
    alert.id = j.value("id", "");
    auto timestamp_val = j.value("timestamp", 0L);
    alert.timestamp = std::chrono::system_clock::from_time_t(timestamp_val);
    alert.severity = severity_from_string(j.value("severity", "info"));
    alert.type = alert_type_from_string(j.value("type", "system_error"));
    alert.title = j.value("title", "");
    alert.description = j.value("description", "");
    alert.acknowledged = j.value("acknowledged", false);
    alert.metadata = j.value("metadata", std::map<std::string, std::string>{});
    return alert;
}

AlertManagerImpl::AlertManagerImpl() {
    Logger::info("AlertManager", "Initialized");
}

std::string AlertManagerImpl::generate_alert_id() {
    uuid_t uuid;
    char uuid_str[37];
    uuid_generate(uuid);
    uuid_unparse(uuid, uuid_str);
    return std::string(uuid_str);
}

std::string AlertManagerImpl::create_alert(
    AlertSeverity severity,
    AlertType type,
    const std::string& title,
    const std::string& description,
    const std::map<std::string, std::string>& metadata) {

    std::lock_guard<std::mutex> lock(alerts_mutex);

    Alert alert;
    alert.id = generate_alert_id();
    alert.timestamp = std::chrono::system_clock::now();
    alert.severity = severity;
    alert.type = type;
    alert.title = title;
    alert.description = description;
    alert.metadata = metadata;
    alert.acknowledged = false;

    alerts.push_back(alert);

    Logger::info("AlertManager", "Created alert: " + alert.id + " - " + title);
    return alert.id;
}

std::vector<Alert> AlertManagerImpl::get_active_alerts() {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    std::vector<Alert> active;
    for (const auto& alert : alerts) {
        if (!alert.acknowledged) {
            active.push_back(alert);
        }
    }
    return active;
}

std::vector<Alert> AlertManagerImpl::get_alerts_by_severity(AlertSeverity severity) {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    std::vector<Alert> result;
    for (const auto& alert : alerts) {
        if (alert.severity == severity && !alert.acknowledged) {
            result.push_back(alert);
        }
    }
    return result;
}

std::vector<Alert> AlertManagerImpl::get_alerts_by_type(AlertType type) {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    std::vector<Alert> result;
    for (const auto& alert : alerts) {
        if (alert.type == type && !alert.acknowledged) {
            result.push_back(alert);
        }
    }
    return result;
}

bool AlertManagerImpl::acknowledge_alert(const std::string& alert_id) {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    for (auto& alert : alerts) {
        if (alert.id == alert_id) {
            alert.acknowledged = true;
            Logger::info("AlertManager", "Acknowledged alert: " + alert_id);
            return true;
        }
    }
    return false;
}

void AlertManagerImpl::clear_acknowledged_alerts() {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    alerts.erase(
        std::remove_if(alerts.begin(), alerts.end(),
                      [](const Alert& a) { return a.acknowledged; }),
        alerts.end()
    );
    Logger::info("AlertManager", "Cleared acknowledged alerts");
}

int AlertManagerImpl::get_alert_count() {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    return alerts.size();
}

json AlertManagerImpl::export_alerts_json() {
    std::lock_guard<std::mutex> lock(this->alerts_mutex);
    json j = json::array();
    for (const auto& alert : alerts) {
        j.push_back(alert.to_json());
    }
    return j;
}

} // namespace daemon
} // namespace cortex
