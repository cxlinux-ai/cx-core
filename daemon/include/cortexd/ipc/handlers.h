/**
 * @file handlers.h
 * @brief IPC request handlers
 */

#pragma once

#include "cortexd/ipc/server.h"
#include "cortexd/ipc/protocol.h"

namespace cortexd {

/**
 * @brief IPC request handlers
 */
class Handlers {
public:
    /**
     * @brief Register all handlers with IPC server
     */
    static void register_all(IPCServer& server);
    
private:
    // Handler implementations
    static Response handle_ping(const Request& req);
    static Response handle_version(const Request& req);
    
    // Config handlers
    static Response handle_config_get(const Request& req);
    static Response handle_config_reload(const Request& req);
    
    // Daemon control
    static Response handle_shutdown(const Request& req);
};

} // namespace cortexd