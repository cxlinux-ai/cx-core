/**
 * @file handlers.cpp
 * @brief IPC request handler implementations
 */

#include "cortexd/ipc/handlers.h"
#include "cortexd/core/daemon.h"
#include "cortexd/monitor/system_monitor.h"
#include "cortexd/alerts/alert_manager.h"
#include "cortexd/config.h"
#include "cortexd/logger.h"

namespace cortexd {

void Handlers::register_all(
    IPCServer& server,
    SystemMonitor& monitor,
    std::shared_ptr<AlertManager> alerts) {
    
    // Basic handlers
    server.register_handler(Methods::PING, [](const Request& req) {
        return handle_ping(req);
    });
    
    server.register_handler(Methods::VERSION, [](const Request& req) {
        return handle_version(req);
    });
    
    server.register_handler(Methods::STATUS, [&monitor, alerts](const Request& req) {
        return handle_status(req, monitor, alerts);
    });
    
    server.register_handler(Methods::HEALTH, [&monitor, alerts](const Request& req) {
        return handle_health(req, monitor, alerts);
    });
    
    // Alert handlers
    server.register_handler(Methods::ALERTS, [alerts](const Request& req) {
        return handle_alerts(req, alerts);
    });
    
    server.register_handler(Methods::ALERTS_GET, [alerts](const Request& req) {
        return handle_alerts(req, alerts);
    });
    
    server.register_handler(Methods::ALERTS_ACK, [alerts](const Request& req) {
        return handle_alerts_ack(req, alerts);
    });
    
    server.register_handler(Methods::ALERTS_DISMISS, [alerts](const Request& req) {
        return handle_alerts_dismiss(req, alerts);
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
    
    LOG_INFO("Handlers", "Registered 10 IPC handlers");
}

Response Handlers::handle_ping(const Request& /*req*/) {
    return Response::ok({{"pong", true}});
}

Response Handlers::handle_status(const Request& /*req*/, SystemMonitor& monitor, std::shared_ptr<AlertManager> alerts) {
    auto& daemon = Daemon::instance();
    auto snapshot = monitor.get_snapshot();
    
    // Override alert counts with fresh values from AlertManager
    if (alerts) {
        snapshot.active_alerts = alerts->count_active();
        snapshot.critical_alerts = alerts->count_by_severity(AlertSeverity::CRITICAL);
    }
    
    // Get LLM backend info from config
    const auto& config = ConfigManager::instance().get();
    json llm_info = {
        {"backend", config.llm_backend},
        {"enabled", config.enable_ai_alerts && config.llm_backend != "none"}
    };
    
    if (config.llm_backend == "local") {
        llm_info["url"] = config.llm_api_url;
    }
    
    json result = {
        {"version", VERSION},
        {"uptime_seconds", daemon.uptime().count()},
        {"running", daemon.is_running()},
        {"health", snapshot.to_json()},
        {"llm", llm_info}
    };
    
    return Response::ok(result);
}

Response Handlers::handle_health(const Request& /*req*/, SystemMonitor& monitor, std::shared_ptr<AlertManager> alerts) {
    auto snapshot = monitor.get_snapshot();
    
    // If snapshot seems uninitialized (timestamp is epoch), force a sync check
    if (snapshot.timestamp == TimePoint{}) {
        LOG_DEBUG("Handlers", "Running forced health check (snapshot empty)");
        snapshot = monitor.force_check();
    }
    
    // Override alert counts with fresh values from AlertManager
    if (alerts) {
        snapshot.active_alerts = alerts->count_active();
        snapshot.critical_alerts = alerts->count_by_severity(AlertSeverity::CRITICAL);
    }
    
    return Response::ok(snapshot.to_json());
}

Response Handlers::handle_version(const Request& /*req*/) {
    return Response::ok({
        {"version", VERSION},
        {"name", NAME}
    });
}

Response Handlers::handle_alerts(const Request& req, std::shared_ptr<AlertManager> alerts) {
    if (!alerts) {
        return Response::err("Alert manager not available", ErrorCodes::INTERNAL_ERROR);
    }
    
    // Check for filters
    std::string severity_filter;
    std::string type_filter;
    int limit = 100;
    
    if (req.params.contains("severity")) {
        severity_filter = req.params["severity"].get<std::string>();
    }
    if (req.params.contains("type")) {
        type_filter = req.params["type"].get<std::string>();
    }
    if (req.params.contains("limit")) {
        limit = req.params["limit"].get<int>();
    }
    
    std::vector<Alert> alert_list;
    
    if (!severity_filter.empty()) {
        alert_list = alerts->get_by_severity(severity_from_string(severity_filter));
    } else if (!type_filter.empty()) {
        alert_list = alerts->get_by_type(alert_type_from_string(type_filter));
    } else {
        alert_list = alerts->get_active();
    }
    
    // Limit results
    if (static_cast<int>(alert_list.size()) > limit) {
        alert_list.resize(limit);
    }
    
    json alerts_json = json::array();
    for (const auto& alert : alert_list) {
        alerts_json.push_back(alert.to_json());
    }
    
    return Response::ok({
        {"alerts", alerts_json},
        {"count", alerts_json.size()},
        {"total_active", alerts->count_active()}
    });
}

Response Handlers::handle_alerts_ack(const Request& req, std::shared_ptr<AlertManager> alerts) {
    if (!alerts) {
        return Response::err("Alert manager not available", ErrorCodes::INTERNAL_ERROR);
    }
    
    if (req.params.contains("id")) {
        std::string id = req.params["id"].get<std::string>();
        if (alerts->acknowledge(id)) {
            return Response::ok({{"acknowledged", id}});
        }
        return Response::err("Alert not found", ErrorCodes::ALERT_NOT_FOUND);
    }
    
    if (req.params.contains("all") && req.params["all"].get<bool>()) {
        int count = alerts->acknowledge_all();
        return Response::ok({{"acknowledged_count", count}});
    }
    
    return Response::err("Missing 'id' or 'all' parameter", ErrorCodes::INVALID_PARAMS);
}

Response Handlers::handle_alerts_dismiss(const Request& req, std::shared_ptr<AlertManager> alerts) {
    if (!alerts) {
        return Response::err("Alert manager not available", ErrorCodes::INTERNAL_ERROR);
    }
    
    if (!req.params.contains("id")) {
        return Response::err("Missing 'id' parameter", ErrorCodes::INVALID_PARAMS);
    }
    
    std::string id = req.params["id"].get<std::string>();
    if (alerts->dismiss(id)) {
        return Response::ok({{"dismissed", id}});
    }
    
    return Response::err("Alert not found", ErrorCodes::ALERT_NOT_FOUND);
}

Response Handlers::handle_config_get(const Request& /*req*/) {
    const auto& config = ConfigManager::instance().get();
    
    json result = {
        {"socket_path", config.socket_path},
        {"llm_backend", config.llm_backend},
        {"llm_api_url", config.llm_api_url},
        {"monitor_interval_sec", config.monitor_interval_sec},
        {"log_level", config.log_level},
        {"enable_ai_alerts", config.enable_ai_alerts},
        {"thresholds", {
            {"disk_warn", config.disk_warn_threshold},
            {"disk_crit", config.disk_crit_threshold},
            {"mem_warn", config.mem_warn_threshold},
            {"mem_crit", config.mem_crit_threshold}
        }}
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

} // namespace cortexd
