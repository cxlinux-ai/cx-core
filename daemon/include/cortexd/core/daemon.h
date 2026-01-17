/**
 * @file daemon.h
 * @brief Main daemon class - coordinates all services
 */

 #pragma once

 #include "cortexd/core/service.h"
 #include "cortexd/config.h"
 #include "cortexd/common.h"
 #include <memory>
 #include <vector>
 #include <atomic>
 #include <chrono>
 #include <functional>
 
 namespace cortexd {
 
// Forward declarations
class IPCServer;
 
 /**
  * @brief Main daemon coordinator
  * 
  * The Daemon class is a singleton that manages the lifecycle of all services,
  * handles signals, and coordinates graceful shutdown.
  */
 class Daemon {
 public:
     /**
      * @brief Get singleton instance
      */
     static Daemon& instance();
     
     /**
      * @brief Initialize the daemon with configuration
      * @param config_path Path to YAML configuration file
      * @return true if initialization successful
      */
     bool initialize(const std::string& config_path);
     
     /**
      * @brief Run the daemon main loop
      * @return Exit code (0 = success)
      * 
      * This method blocks until shutdown is requested.
      */
     int run();
     
     /**
      * @brief Request graceful shutdown
      */
     void request_shutdown();
     
     /**
      * @brief Check if daemon is running
      */
     bool is_running() const { return running_.load(); }
     
     /**
      * @brief Check if shutdown was requested
      */
     bool shutdown_requested() const { return shutdown_requested_.load(); }
     
     /**
      * @brief Register a service with the daemon
      * @param service Service to register
      */
     void register_service(std::unique_ptr<Service> service);
     
     /**
      * @brief Get service by type
      * @return Pointer to service or nullptr if not found
      */
     template<typename T>
     T* get_service() {
         for (auto& svc : services_) {
             if (auto* ptr = dynamic_cast<T*>(svc.get())) {
                 return ptr;
             }
         }
         return nullptr;
     }
     
     /**
      * @brief Get current configuration (returns copy for thread safety)
      */
     Config config() const;
     
     /**
      * @brief Get daemon uptime
      */
     std::chrono::seconds uptime() const;
     
     /**
      * @brief Notify systemd that daemon is ready
      */
     void notify_ready();
     
     /**
      * @brief Notify systemd that daemon is stopping
      */
     void notify_stopping();
     
     /**
      * @brief Send watchdog keepalive to systemd
      */
     void notify_watchdog();
     
    /**
     * @brief Reload configuration
     * @return true if successful
     */
    bool reload_config();
    
    /**
     * @brief Reset daemon state for testing
     * 
     * Clears all registered services and resets shutdown flag.
     * Should only be used in test teardown to ensure clean state between tests.
     */
    void reset();
    
    // Delete copy/move
    Daemon(const Daemon&) = delete;
    Daemon& operator=(const Daemon&) = delete;
     
 private:
     Daemon() = default;
     
     std::vector<std::unique_ptr<Service>> services_;
     std::atomic<bool> running_{false};
     std::atomic<bool> shutdown_requested_{false};
     std::chrono::steady_clock::time_point start_time_;
     
     /**
      * @brief Setup signal handlers
      */
     void setup_signals();
     
     /**
      * @brief Start all registered services
      * @return true if all services started
      */
     bool start_services();
     
     /**
      * @brief Stop all running services
      */
     void stop_services();
     
     /**
      * @brief Main event loop iteration
      */
     void event_loop();
 };
 
 } // namespace cortexd
 