/**
 * @file handlers.cpp
 * @brief IPC request handler implementations
 */

#include "cortexd/ipc/handlers.h"
#include "cortexd/core/daemon.h"
#include "cortexd/config.h"
#include "cortexd/logger.h"

namespace cortexd {

void Handlers::register_all(IPCServer& server) {
    // Basic handlers only
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
    
    LOG_INFO("Handlers", "Registered 5 core IPC handlers");
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

} // namespace cortexd