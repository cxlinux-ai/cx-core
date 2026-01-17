/**
 * @file server.cpp
 * @brief Unix socket IPC server implementation
 */

 #include "cortexd/ipc/server.h"
 #include "cortexd/logger.h"
 #include <sys/socket.h>
 #include <sys/un.h>
 #include <sys/stat.h>
 #include <unistd.h>
 #include <fcntl.h>
 #include <cstring>
 #include <filesystem>
 
 namespace cortexd {
 
 // RateLimiter implementation
 
 RateLimiter::RateLimiter(int max_per_second)
     : max_per_second_(max_per_second)
     , window_start_(std::chrono::steady_clock::now()) {
 }
 
 bool RateLimiter::allow() {
     std::lock_guard<std::mutex> lock(mutex_);
     
     auto now = std::chrono::steady_clock::now();
     auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - window_start_);
     
     // Reset window every second
     if (elapsed.count() >= 1000) {
         count_ = 0;
         window_start_ = now;
     }
     
     if (count_ >= max_per_second_) {
         return false;
     }
     
     count_++;
     return true;
 }
 
 void RateLimiter::reset() {
     std::lock_guard<std::mutex> lock(mutex_);
     count_ = 0;
     window_start_ = std::chrono::steady_clock::now();
 }
 
 // IPCServer implementation
 
 IPCServer::IPCServer(const std::string& socket_path, int max_requests_per_sec)
     : socket_path_(socket_path)
     , rate_limiter_(max_requests_per_sec) {
 }
 
 IPCServer::~IPCServer() {
     stop();
 }
 
 bool IPCServer::start() {
     if (running_) {
         return true;
     }
     
     if (!create_socket()) {
         return false;
     }
     
     running_ = true;
     accept_thread_ = std::make_unique<std::thread>([this] { accept_loop(); });
     
     LOG_INFO("IPCServer", "Started on " + socket_path_);
     return true;
 }
 
 void IPCServer::stop() {
     if (!running_) {
         return;
     }
     
     running_ = false;
     
     // Shutdown socket to unblock accept() and stop new connections
     if (server_fd_ != -1) {
         shutdown(server_fd_, SHUT_RDWR);
     }
     
     // Wait for accept thread
     if (accept_thread_ && accept_thread_->joinable()) {
         accept_thread_->join();
     }
     
     // Wait for all in-flight handlers to finish before cleanup
     // This prevents dangling references to server state
     {
         std::unique_lock<std::mutex> lock(connections_mutex_);
         connections_cv_.wait(lock, [this] {
             return active_connections_.load() == 0;
         });
     }
     
     cleanup_socket();
     LOG_INFO("IPCServer", "Stopped");
 }
 
 bool IPCServer::is_healthy() const {
     return running_.load() && server_fd_ != -1;
 }
 
 void IPCServer::register_handler(const std::string& method, RequestHandler handler) {
     std::lock_guard<std::mutex> lock(handlers_mutex_);
     handlers_[method] = std::move(handler);
     LOG_DEBUG("IPCServer", "Registered handler for: " + method);
 }
 
 bool IPCServer::create_socket() {
     // Create socket
     server_fd_ = socket(AF_UNIX, SOCK_STREAM, 0);
     if (server_fd_ == -1) {
         LOG_ERROR("IPCServer", "Failed to create socket: " + std::string(strerror(errno)));
         return false;
     }
     
     // Set socket options
     int opt = 1;
     setsockopt(server_fd_, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
     
     // Remove existing socket file
     if (std::filesystem::exists(socket_path_)) {
         std::filesystem::remove(socket_path_);
         LOG_DEBUG("IPCServer", "Removed existing socket file");
     }
     
     // Create parent directory if needed
     auto parent = std::filesystem::path(socket_path_).parent_path();
     if (!parent.empty() && !std::filesystem::exists(parent)) {
         std::filesystem::create_directories(parent);
     }
     
    // Bind socket
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    
    // Check socket path length before copying to prevent silent truncation
    if (socket_path_.size() > sizeof(addr.sun_path) - 1) {
        LOG_ERROR("IPCServer", "Socket path too long: " + socket_path_ + " (max " + 
                  std::to_string(sizeof(addr.sun_path) - 1) + " bytes)");
        close(server_fd_);
        server_fd_ = -1;
        return false;
    }
    
    strncpy(addr.sun_path, socket_path_.c_str(), sizeof(addr.sun_path) - 1);
    addr.sun_path[sizeof(addr.sun_path) - 1] = '\0';  // Ensure null termination
    
    if (bind(server_fd_, (struct sockaddr*)&addr, sizeof(addr)) == -1) {
        LOG_ERROR("IPCServer", "Failed to bind socket: " + std::string(strerror(errno)));
        close(server_fd_);
        server_fd_ = -1;
        return false;
    }
     
     // Listen
     if (listen(server_fd_, SOCKET_BACKLOG) == -1) {
         LOG_ERROR("IPCServer", "Failed to listen: " + std::string(strerror(errno)));
         close(server_fd_);
         server_fd_ = -1;
         return false;
     }
     
     return setup_permissions();
 }
 
bool IPCServer::setup_permissions() {
    // Set socket permissions to 0666 (world read/write)
    // This is safe for Unix domain sockets as they are local-only (not network accessible).
    // The socket directory (/run/cortex/) provides additional access control if needed.
    if (chmod(socket_path_.c_str(), 0666) == -1) {
        LOG_WARN("IPCServer", "Failed to set socket permissions: " + std::string(strerror(errno)));
        // Continue anyway
    }
    return true;
}
 
 void IPCServer::cleanup_socket() {
     if (server_fd_ != -1) {
         close(server_fd_);
         server_fd_ = -1;
     }
     
     if (std::filesystem::exists(socket_path_)) {
         std::filesystem::remove(socket_path_);
     }
 }
 
 void IPCServer::accept_loop() {
     LOG_DEBUG("IPCServer", "Accept loop started");
     
     while (running_) {
         int client_fd = accept(server_fd_, nullptr, nullptr);
         
         if (client_fd == -1) {
             if (running_) {
                 LOG_ERROR("IPCServer", "Accept failed: " + std::string(strerror(errno)));
             }
             continue;
         }
         
         // Set socket timeout
         struct timeval timeout;
         timeout.tv_sec = SOCKET_TIMEOUT_MS / 1000;
         timeout.tv_usec = (SOCKET_TIMEOUT_MS % 1000) * 1000;
         setsockopt(client_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
         setsockopt(client_fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
         
         // Handle client (could be async in future)
         handle_client(client_fd);
     }
     
     LOG_DEBUG("IPCServer", "Accept loop ended");
 }
 
 void IPCServer::handle_client(int client_fd) {
     {
         std::lock_guard<std::mutex> lock(connections_mutex_);
         active_connections_++;
         connections_served_++;
     }
     
     try {
         // Read request - use heap allocation for large buffer to avoid stack overflow
         // if we ever move to threaded handling
         std::vector<char> buffer(MAX_MESSAGE_SIZE);
         ssize_t bytes = recv(client_fd, buffer.data(), buffer.size() - 1, 0);
         
         if (bytes <= 0) {
             LOG_DEBUG("IPCServer", "Client disconnected without data");
             close(client_fd);
             {
                 std::lock_guard<std::mutex> lock(connections_mutex_);
                 active_connections_--;
             }
             connections_cv_.notify_all();
             return;
         }
         
         buffer[bytes] = '\0';
         std::string raw_request(buffer.data());
         LOG_DEBUG("IPCServer", "Received: " + raw_request);
         
         // Check rate limit
         if (!rate_limiter_.allow()) {
             LOG_WARN("IPCServer", "Rate limit exceeded");
             auto resp = Response::err("Rate limit exceeded", ErrorCodes::RATE_LIMITED);
             std::string response_str = resp.to_json();
             send(client_fd, response_str.c_str(), response_str.length(), 0);
             close(client_fd);
             {
                 std::lock_guard<std::mutex> lock(connections_mutex_);
                 active_connections_--;
             }
             connections_cv_.notify_all();
             return;
         }
         
         // Parse request
         auto request = Request::parse(raw_request);
         Response response;
         
         if (!request) {
             response = Response::err("Invalid request format", ErrorCodes::PARSE_ERROR);
         } else {
             response = dispatch(*request);
         }
         
         // Send response
         std::string response_str = response.to_json();
         LOG_DEBUG("IPCServer", "Sending: " + response_str);
         
         if (send(client_fd, response_str.c_str(), response_str.length(), 0) == -1) {
             LOG_ERROR("IPCServer", "Failed to send response: " + std::string(strerror(errno)));
         }
         
     } catch (const std::exception& e) {
         LOG_ERROR("IPCServer", "Exception handling client: " + std::string(e.what()));
         auto resp = Response::err(e.what(), ErrorCodes::INTERNAL_ERROR);
         std::string response_str = resp.to_json();
         send(client_fd, response_str.c_str(), response_str.length(), 0);
     }
     
     close(client_fd);
     {
         std::lock_guard<std::mutex> lock(connections_mutex_);
         active_connections_--;
     }
     connections_cv_.notify_all();
 }
 
 Response IPCServer::dispatch(const Request& request) {
     RequestHandler handler;
     {
         std::lock_guard<std::mutex> lock(handlers_mutex_);
         
         auto it = handlers_.find(request.method);
         if (it == handlers_.end()) {
             LOG_WARN("IPCServer", "Unknown method: " + request.method);
             return Response::err("Method not found: " + request.method, ErrorCodes::METHOD_NOT_FOUND);
         }
         
         // Copy handler to execute outside the lock
         handler = it->second;
     }
     
     // Execute handler without holding the mutex to prevent deadlock
     // if handler calls back into server (e.g., registering another handler)
     LOG_INFO("IPCServer", "Handler found, invoking...");
     try {
         Response resp = handler(request);
         LOG_INFO("IPCServer", "Handler completed successfully");
         return resp;
     } catch (const std::exception& e) {
         LOG_ERROR("IPCServer", "Handler error for " + request.method + ": " + e.what());
         return Response::err(e.what(), ErrorCodes::INTERNAL_ERROR);
     }
 }
 
 } // namespace cortexd
 