#include "socket_server.h"
#include "ipc_protocol.h"
#include "logging.h"
#include "system_monitor.h"
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstring>
#include <filesystem>

namespace cortex {
namespace daemon {

SocketServer::SocketServer(const std::string& socket_path)
    : socket_path_(socket_path), server_fd_(-1), running_(false) {
}

SocketServer::~SocketServer() {
    stop();
}

bool SocketServer::create_socket() {
    server_fd_ = socket(AF_UNIX, SOCK_STREAM, 0);
    if (server_fd_ == -1) {
        Logger::error("SocketServer", "Failed to create socket: " + std::string(strerror(errno)));
        return false;
    }

    // Remove existing socket file if it exists
    if (std::filesystem::exists(socket_path_)) {
        std::filesystem::remove(socket_path_);
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, socket_path_.c_str(), sizeof(addr.sun_path) - 1);

    if (bind(server_fd_, (struct sockaddr*)&addr, sizeof(addr)) == -1) {
        Logger::error("SocketServer", "Failed to bind socket: " + std::string(strerror(errno)));
        close(server_fd_);
        server_fd_ = -1;
        return false;
    }

    if (listen(server_fd_, SOCKET_BACKLOG) == -1) {
        Logger::error("SocketServer", "Failed to listen: " + std::string(strerror(errno)));
        close(server_fd_);
        server_fd_ = -1;
        return false;
    }

    return setup_permissions();
}

bool SocketServer::setup_permissions() {
    // Set socket permissions to 0666 so CLI can connect
    if (chmod(socket_path_.c_str(), 0666) == -1) {
        Logger::warn("SocketServer", "Failed to set socket permissions: " + std::string(strerror(errno)));
        // Continue anyway, but this is a warning
    }
    return true;
}

void SocketServer::cleanup_socket() {
    if (server_fd_ != -1) {
        close(server_fd_);
        server_fd_ = -1;
    }
    if (std::filesystem::exists(socket_path_)) {
        std::filesystem::remove(socket_path_);
    }
}

bool SocketServer::start() {
    if (running_) {
        return true;
    }

    if (!create_socket()) {
        return false;
    }

    running_ = true;
    accept_thread_ = std::make_unique<std::thread>([this] { accept_connections(); });
    Logger::info("SocketServer", "Socket server started");

    return true;
}

void SocketServer::stop() {
    if (!running_) {
        return;
    }

    running_ = false;

    if (server_fd_ != -1) {
        shutdown(server_fd_, SHUT_RDWR);
    }

    if (accept_thread_ && accept_thread_->joinable()) {
        accept_thread_->join();
    }

    cleanup_socket();
    Logger::info("SocketServer", "Socket server stopped");
}

bool SocketServer::is_running() const {
    return running_;
}

void SocketServer::accept_connections() {
    Logger::info("SocketServer", "Accepting connections on " + socket_path_);

    while (running_) {
        int client_fd = accept(server_fd_, nullptr, nullptr);
        if (client_fd == -1) {
            if (running_) {
                Logger::error("SocketServer", "Accept failed: " + std::string(strerror(errno)));
            }
            continue;
        }

        // Set socket timeout
        struct timeval timeout;
        timeout.tv_sec = SOCKET_TIMEOUT_MS / 1000;
        timeout.tv_usec = (SOCKET_TIMEOUT_MS % 1000) * 1000;
        setsockopt(client_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

        // Handle client in this thread (simple synchronous model)
        handle_client(client_fd);
    }
}

void SocketServer::handle_client(int client_fd) {
    const int BUFFER_SIZE = 4096;
    char buffer[BUFFER_SIZE];

    try {
        // Read request
        ssize_t bytes = recv(client_fd, buffer, BUFFER_SIZE - 1, 0);
        if (bytes <= 0) {
            Logger::warn("SocketServer", "Client disconnected without sending data");
            close(client_fd);
            return;
        }

        buffer[bytes] = '\0';
        std::string request(buffer);
        Logger::debug("SocketServer", "Received: " + request);

        // Parse and handle request
        auto [cmd_type, req_json] = IPCProtocol::parse_request(request);

        std::string response;
        switch (cmd_type) {
            case CommandType::STATUS:
                response = IPCProtocol::build_success_response("Status check - TODO");
                break;
            case CommandType::ALERTS:
                response = IPCProtocol::build_alerts_response(nlohmann::json::array());
                break;
            case CommandType::HEALTH: {
                HealthSnapshot health = g_system_monitor->get_health_snapshot();
                response = IPCProtocol::build_health_response(health);
                break;
            }
            case CommandType::SHUTDOWN:
                response = IPCProtocol::build_success_response("Shutdown requested");
                break;
            case CommandType::CONFIG_RELOAD:
                response = IPCProtocol::build_success_response("Config reloaded");
                break;
            default:
                response = IPCProtocol::build_error_response("Unknown command");
                break;
        }

        // Send response
        if (send(client_fd, response.c_str(), response.length(), 0) == -1) {
            Logger::error("SocketServer", "Failed to send response: " + std::string(strerror(errno)));
        }

    } catch (const std::exception& e) {
        Logger::error("SocketServer", "Exception handling client: " + std::string(e.what()));
        std::string error_resp = IPCProtocol::build_error_response(e.what());
        send(client_fd, error_resp.c_str(), error_resp.length(), 0);
    }

    close(client_fd);
}

} // namespace daemon
} // namespace cortex
