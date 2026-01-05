#pragma once

#include <string>
#include <vector>
#include <memory>
#include <map>
#include <mutex>
#include <nlohmann/json.hpp>
#include "cortexd_common.h"

namespace cortex {
namespace daemon {

using json = nlohmann::json;

// Alert structure
struct Alert {
    std::string id;
    std::chrono::system_clock::time_point timestamp;
    AlertSeverity severity;
    AlertType type;
    std::string title;
    std::string description;
    std::map<std::string, std::string> metadata;
    bool acknowledged = false;

    json to_json() const;
    static Alert from_json(const json& j);
};

// Alert manager interface
class AlertManager {
public:
    virtual ~AlertManager() = default;

    // Create and store a new alert
    virtual std::string create_alert(
        AlertSeverity severity,
        AlertType type,
        const std::string& title,
        const std::string& description,
        const std::map<std::string, std::string>& metadata = {}
    ) = 0;

    // Get all active alerts
    virtual std::vector<Alert> get_active_alerts() = 0;

    // Get alerts by severity
    virtual std::vector<Alert> get_alerts_by_severity(AlertSeverity severity) = 0;

    // Get alerts by type
    virtual std::vector<Alert> get_alerts_by_type(AlertType type) = 0;

    // Acknowledge an alert
    virtual bool acknowledge_alert(const std::string& alert_id) = 0;

    // Clear all acknowledged alerts
    virtual void clear_acknowledged_alerts() = 0;

    // Get alert count
    virtual int get_alert_count() = 0;

    // Export alerts as JSON
    virtual json export_alerts_json() = 0;
};

// Concrete implementation
class AlertManagerImpl : public AlertManager {
public:
    AlertManagerImpl();
    ~AlertManagerImpl() = default;

    std::string create_alert(
        AlertSeverity severity,
        AlertType type,
        const std::string& title,
        const std::string& description,
        const std::map<std::string, std::string>& metadata = {}
    ) override;

    std::vector<Alert> get_active_alerts() override;
    std::vector<Alert> get_alerts_by_severity(AlertSeverity severity) override;
    std::vector<Alert> get_alerts_by_type(AlertType type) override;
    bool acknowledge_alert(const std::string& alert_id) override;
    void clear_acknowledged_alerts() override;
    int get_alert_count() override;
    json export_alerts_json() override;

private:
    std::vector<Alert> alerts;
    mutable std::mutex alerts_mutex;

    std::string generate_alert_id();
};

} // namespace daemon
} // namespace cortex
