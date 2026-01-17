/**
 * @file server.h
 * @brief Unix socket IPC server
 */

 #pragma once

 #include "cortexd/core/service.h"
 #include "cortexd/ipc/protocol.h"
 #include <string>
 #include <thread>
 #include <atomic>
 #include <mutex>
 #include <condition_variable>
 #include <functional>
 #include <unordered_map>
 #include <chrono>
 
 namespace cortexd {
 
 /**
  * @brief Request handler function type
  */
 using RequestHandler = std::function<Response(const Request&)>;
 
 /**
  * @brief Rate limiter for request throttling
  */
 class RateLimiter {
 public:
     explicit RateLimiter(int max_per_second);
     
     /**
      * @brief Check if request is allowed
      * @return true if allowed, false if rate limited
      */
     bool allow();
     
     /**
      * @brief Reset the rate limiter
      */
     void reset();
     
 private:
     int max_per_second_;
     int count_ = 0;
     std::chrono::steady_clock::time_point window_start_;
     std::mutex mutex_;
 };
 
 /**
  * @brief Unix socket IPC server
  */
 class IPCServer : public Service {
 public:
     /**
      * @brief Construct server with socket path
      * @param socket_path Path to Unix socket
      * @param max_requests_per_sec Rate limit for requests
      */
     explicit IPCServer(const std::string& socket_path, int max_requests_per_sec = 100);
     ~IPCServer() override;
     
     // Service interface
     bool start() override;
     void stop() override;
     const char* name() const override { return "IPCServer"; }
     int priority() const override { return 100; }  // Start first
     bool is_running() const override { return running_.load(); }
     bool is_healthy() const override;
     
     /**
      * @brief Register a request handler for a method
      * @param method Method name
      * @param handler Handler function
      */
     void register_handler(const std::string& method, RequestHandler handler);
     
     /**
      * @brief Get number of connections served
      */
     size_t connections_served() const { return connections_served_.load(); }
     
     /**
      * @brief Get number of active connections
      */
     size_t active_connections() const { return active_connections_.load(); }
     
 private:
     std::string socket_path_;
     int server_fd_ = -1;
     std::atomic<bool> running_{false};
     std::unique_ptr<std::thread> accept_thread_;
     
     std::unordered_map<std::string, RequestHandler> handlers_;
     std::mutex handlers_mutex_;
     
     RateLimiter rate_limiter_;
     
     std::atomic<size_t> connections_served_{0};
     std::atomic<size_t> active_connections_{0};
     
     // Condition variable for waiting on in-flight handlers during stop()
     std::condition_variable connections_cv_;
     std::mutex connections_mutex_;
     
     /**
      * @brief Create and bind the socket
      */
     bool create_socket();
     
     /**
      * @brief Set socket permissions
      */
     bool setup_permissions();
     
     /**
      * @brief Clean up socket file
      */
     void cleanup_socket();
     
     /**
      * @brief Accept loop running in thread
      */
     void accept_loop();
     
     /**
      * @brief Handle a single client connection
      */
     void handle_client(int client_fd);
     
     /**
      * @brief Dispatch request to handler
      */
     Response dispatch(const Request& request);
 };
 
 } // namespace cortexd
 