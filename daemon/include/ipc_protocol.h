#pragma once

#include <string>
#include <memory>
#include <nlohmann/json.hpp>
#include "cortexd_common.h"

namespace cortex {
namespace daemon {

using json = nlohmann::json;

// IPC Protocol handler
class IPCProtocol {
public:
    IPCProtocol() = default;
    ~IPCProtocol() = default;

    // Parse incoming request
    static std::pair<CommandType, json> parse_request(const std::string& request);

    // Build status response
    static std::string build_status_response(const HealthSnapshot& health);

    // Build alerts response
    static std::string build_alerts_response(const json& alerts_data);

    // Build error response
    static std::string build_error_response(const std::string& error_message);

    // Build success response
    static std::string build_success_response(const std::string& message);

    // Build health snapshot response
    static std::string build_health_response(const HealthSnapshot& health);

private:
    static bool validate_json(const std::string& str);
};

} // namespace daemon
} // namespace cortex
