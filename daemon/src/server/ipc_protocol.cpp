#include "ipc_protocol.h"
#include "logging.h"
#include <nlohmann/json.hpp>

namespace cortex {
namespace daemon {

using json = nlohmann::json;

bool IPCProtocol::validate_json(const std::string& str) {
    try {
        auto parsed = json::parse(str);
        (void)parsed;  // Suppress unused variable warning
        return true;
    } catch (...) {
        return false;
    }
}

std::pair<CommandType, json> IPCProtocol::parse_request(const std::string& request) {
    try {
        if (!validate_json(request)) {
            return {CommandType::UNKNOWN, json()};
        }

        json req = json::parse(request);
        std::string cmd = req.value("command", "");
        CommandType type = command_from_string(cmd);

        return {type, req};
    } catch (const std::exception& e) {
        Logger::error("IPCProtocol", "Failed to parse request: " + std::string(e.what()));
        return {CommandType::UNKNOWN, json()};
    }
}

std::string IPCProtocol::build_status_response(const HealthSnapshot& health) {
    json response;
    response["status"] = "ok";
    response["version"] = DAEMON_VERSION;
    response["uptime_seconds"] = 0; // TODO: implement uptime tracking
    response["health"]["cpu_usage"] = health.cpu_usage;
    response["health"]["memory_usage"] = health.memory_usage;
    response["health"]["disk_usage"] = health.disk_usage;
    response["health"]["active_processes"] = health.active_processes;
    response["health"]["open_files"] = health.open_files;
    response["health"]["llm_loaded"] = health.llm_loaded;
    response["health"]["inference_queue_size"] = health.inference_queue_size;
    response["health"]["alerts_count"] = health.alerts_count;
    response["timestamp"] = std::chrono::system_clock::to_time_t(health.timestamp);

    return response.dump();
}

std::string IPCProtocol::build_alerts_response(const json& alerts_data) {
    json response;
    response["status"] = "ok";
    response["alerts"] = alerts_data;
    response["count"] = alerts_data.is_array() ? alerts_data.size() : 0;
    response["timestamp"] = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());

    return response.dump();
}

std::string IPCProtocol::build_error_response(const std::string& error_message) {
    json response;
    response["status"] = "error";
    response["error"] = error_message;
    response["timestamp"] = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());

    return response.dump();
}

std::string IPCProtocol::build_success_response(const std::string& message) {
    json response;
    response["status"] = "success";
    response["message"] = message;
    response["timestamp"] = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());

    return response.dump();
}

std::string IPCProtocol::build_health_response(const HealthSnapshot& health) {
    json response;
    response["status"] = "ok";
    response["health"] = {
        {"cpu_usage", health.cpu_usage},
        {"memory_usage", health.memory_usage},
        {"disk_usage", health.disk_usage},
        {"active_processes", health.active_processes},
        {"open_files", health.open_files},
        {"llm_loaded", health.llm_loaded},
        {"inference_queue_size", health.inference_queue_size},
        {"alerts_count", health.alerts_count}
    };
    response["timestamp"] = std::chrono::system_clock::to_time_t(health.timestamp);

    return response.dump();
}

} // namespace daemon
} // namespace cortex
