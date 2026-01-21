/**
 * @file handlers.cpp
 * @brief IPC request handler implementations
 */

#include "cortexd/ipc/handlers.h"
#include "cortexd/core/daemon.h"
#include "cortexd/config.h"
#include "cortexd/logger.h"
#include "cortexd/monitor/system_monitor.h"
#include "cortexd/alerts/alert_manager.h"
#include "cortexd/ipc/server.h"

namespace cortexd {

void Handlers::register_all(
    IPCServer& server,
    SystemMonitor* monitor,
    std::shared_ptr<AlertManager> alerts
) {
    // Basic handlers
    server.register_handler(Methods::PING, [](const Request& req) {
        return handle_ping(req);
    });
    
    server.register_handler(Methods::VERSION, [](const Request& req) {
        return handle_version(req);
    });
    
    // Config handlers
    server.register_handler(Methods::CONFIG_GET, [](const Request& req) {
        return handle_config_get(req);
    });
    
    server.register_handler(Methods::CONFIG_RELOAD, [](const Request& req) {
        return handle_config_reload(req);
    });
    
    // Daemon control
    server.register_handler(Methods::SHUTDOWN, [](const Request& req) {
        return handle_shutdown(req);
    });
    
    // Monitoring handlers (if monitor is available)
    if (monitor) {
        server.register_handler(Methods::HEALTH, [monitor](const Request& req) {
            return handle_health(req, monitor);
        });
    }
    
    // Alert handlers (if alerts is available)
    if (alerts) {
        // Both "alerts" and "alerts.get" map to the same handler
        server.register_handler(Methods::ALERTS, [alerts](const Request& req) {
            return handle_alerts_get(req, alerts);
        });
        
        server.register_handler(Methods::ALERTS_GET, [alerts](const Request& req) {
            return handle_alerts_get(req, alerts);
        });
        
        server.register_handler(Methods::ALERTS_ACK, [alerts](const Request& req) {
            return handle_alerts_acknowledge(req, alerts);
        });
        
        server.register_handler(Methods::ALERTS_DISMISS, [alerts](const Request& req) {
            return handle_alerts_dismiss(req, alerts);
        });
    }
    
    int handler_count = 5;  // Core handlers
    if (monitor) handler_count += 1;  // Health
    if (alerts) handler_count += 4;    // Alerts + Alerts get + ack + dismiss
    
    LOG_INFO("Handlers", "Registered " + std::to_string(handler_count) + " IPC handlers");
}

Response Handlers::handle_ping(const Request& /*req*/) {
    return Response::ok({{"pong", true}});
}

Response Handlers::handle_version(const Request& /*req*/) {
    return Response::ok({
        {"version", VERSION},
        {"name", NAME}
    });
}

Response Handlers::handle_config_get(const Request& /*req*/) {
    const auto& config = ConfigManager::instance().get();
    
    // PR 1: Return only core daemon configuration
    json result = {
        {"socket_path", config.socket_path},
        {"socket_backlog", config.socket_backlog},
        {"socket_timeout_ms", config.socket_timeout_ms},
        {"max_requests_per_sec", config.max_requests_per_sec},
        {"log_level", config.log_level}
    };
    
    return Response::ok(result);
}

Response Handlers::handle_config_reload(const Request& /*req*/) {
    if (Daemon::instance().reload_config()) {
        return Response::ok({{"reloaded", true}});
    }
    return Response::err("Failed to reload configuration", ErrorCodes::CONFIG_ERROR);
}

Response Handlers::handle_shutdown(const Request& /*req*/) {
    LOG_INFO("Handlers", "Shutdown requested via IPC");
    Daemon::instance().request_shutdown();
    return Response::ok({{"shutdown", "initiated"}});
}

Response Handlers::handle_health(const Request& /*req*/, SystemMonitor* monitor) {
    if (!monitor) {
        return Response::err("System monitor not available", ErrorCodes::INTERNAL_ERROR);
    }
    
    SystemHealth health = monitor->get_health();
    MonitoringThresholds thresholds = monitor->get_thresholds();
    
    json result = health.to_json();
    result["thresholds"] = {
        {"cpu", {
            {"warning", thresholds.cpu_warning},
            {"critical", thresholds.cpu_critical}
        }},
        {"memory", {
            {"warning", thresholds.memory_warning},
            {"critical", thresholds.memory_critical}
        }},
        {"disk", {
            {"warning", thresholds.disk_warning},
            {"critical", thresholds.disk_critical}
        }}
    };
    
    return Response::ok(result);
}

Response Handlers::handle_alerts_get(const Request& req, std::shared_ptr<AlertManager> alerts) {
    if (!alerts) {
        return Response::err("Alert manager not available", ErrorCodes::INTERNAL_ERROR);
    }
    
    AlertFilter filter;
    filter.include_dismissed = false;  // Default: don't include dismissed
    
    // Parse filter parameters
    if (req.params.is_object()) {
        if (req.params.contains("severity")) {
            std::string severity_str = req.params["severity"].get<std::string>();
            filter.severity = AlertManager::string_to_severity(severity_str);
        }
        
        if (req.params.contains("category")) {
            std::string category_str = req.params["category"].get<std::string>();
            filter.category = AlertManager::string_to_category(category_str);
        }
        
        if (req.params.contains("status")) {
            std::string status_str = req.params["status"].get<std::string>();
            filter.status = AlertManager::string_to_status(status_str);
        }
        
        if (req.params.contains("source")) {
            std::string source_str = req.params["source"].get<std::string>();
            filter.source = source_str;
        }
        
        if (req.params.contains("include_dismissed")) {
            filter.include_dismissed = req.params["include_dismissed"].get<bool>();
        }
    }
    
    auto alert_list = alerts->get_alerts(filter);
    json alerts_json = json::array();
    
    for (const auto& alert : alert_list) {
        alerts_json.push_back(alert.to_json());
    }
    
    json result;
    result["alerts"] = alerts_json;
    result["count"] = alert_list.size();
    result["counts"] = alerts->get_alert_counts();
    
    return Response::ok(result);
}

Response Handlers::handle_alerts_acknowledge(const Request& req, std::shared_ptr<AlertManager> alerts) {
    if (!alerts) {
        return Response::err("Alert manager not available", ErrorCodes::INTERNAL_ERROR);
    }
    
    // Check if acknowledging all or specific UUID
    if (req.params.is_object() && req.params.contains("all") && req.params["all"].get<bool>()) {
        size_t count = alerts->acknowledge_all();
        return Response::ok({
            {"acknowledged", count},
            {"message", "Acknowledged " + std::to_string(count) + " alert(s)"}
        });
    } else if (req.params.is_object() && req.params.contains("uuid")) {
        std::string uuid = req.params["uuid"].get<std::string>();
        if (alerts->acknowledge_alert(uuid)) {
            return Response::ok({
                {"acknowledged", true},
                {"uuid", uuid}
            });
        } else {
            return Response::err("Alert not found or already acknowledged", ErrorCodes::ALERT_NOT_FOUND);
        }
    } else {
        // Default: acknowledge all
        size_t count = alerts->acknowledge_all();
        return Response::ok({
            {"acknowledged", count},
            {"message", "Acknowledged " + std::to_string(count) + " alert(s)"}
        });
    }
}

Response Handlers::handle_alerts_dismiss(const Request& req, std::shared_ptr<AlertManager> alerts) {
    if (!alerts) {
        return Response::err("Alert manager not available", ErrorCodes::INTERNAL_ERROR);
    }
    
    // Check if dismissing all or specific UUID
    if (req.params.is_object() && req.params.contains("all") && req.params["all"].get<bool>()) {
        size_t count = alerts->dismiss_all();
        return Response::ok({
            {"dismissed", count},
            {"message", "Dismissed " + std::to_string(count) + " alert(s)"}
        });
    } else if (req.params.is_object() && req.params.contains("uuid")) {
        std::string uuid = req.params["uuid"].get<std::string>();
        if (alerts->dismiss_alert(uuid)) {
            return Response::ok({
                {"dismissed", true},
                {"uuid", uuid}
            });
        } else {
            return Response::err("Alert not found", ErrorCodes::ALERT_NOT_FOUND);
        }
    } else {
        return Response::err("UUID or 'all' parameter required for dismiss", ErrorCodes::INVALID_PARAMS);
    }
}

} // namespace cortexd