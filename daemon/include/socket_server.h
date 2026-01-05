#pragma once

#include <string>
#include <memory>
#include <thread>
#include <atomic>
#include "cortexd_common.h"

namespace cortex {
namespace daemon {

// Unix socket server
class SocketServer {
public:
    SocketServer(const std::string& socket_path = SOCKET_PATH);
    ~SocketServer();

    // Start listening on socket
    bool start();

    // Stop the server
    void stop();

    // Check if running
    bool is_running() const;

    // Get socket path
    const std::string& get_socket_path() const { return socket_path_; }

private:
    std::string socket_path_;
    int server_fd_;
    std::atomic<bool> running_;
    std::unique_ptr<std::thread> accept_thread_;

    // Accept connections and handle requests
    void accept_connections();

    // Handle single client connection
    void handle_client(int client_fd);

    // Create Unix socket
    bool create_socket();

    // Setup socket permissions
    bool setup_permissions();

    // Cleanup socket file
    void cleanup_socket();
};

} // namespace daemon
} // namespace cortex
