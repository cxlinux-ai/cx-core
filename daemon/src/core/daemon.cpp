/**
 * @file daemon.cpp
 * @brief Main daemon implementation
 */

 #include "cortexd/core/daemon.h"
 #include "cortexd/logger.h"
 #include <algorithm>
 #include <thread>
 #include <signal.h>
 #include <systemd/sd-daemon.h>
 
 namespace cortexd {
 
 // Volatile flags for async-signal-safe signal handling
 // Signal handlers should only set flags, not call complex functions
 static volatile sig_atomic_t g_shutdown_requested = 0;
 static volatile sig_atomic_t g_reload_requested = 0;
 
 // Signal handler function - only sets flags (async-signal-safe)
 static void signal_handler(int sig) {
     if (sig == SIGTERM || sig == SIGINT) {
         g_shutdown_requested = 1;
     } else if (sig == SIGHUP) {
         g_reload_requested = 1;
     }
 }
 
 Daemon& Daemon::instance() {
     static Daemon instance;
     return instance;
 }
 
 bool Daemon::initialize(const std::string& config_path) {
     LOG_INFO("Daemon", "Initializing cortexd version " + std::string(VERSION));
     
     // Load configuration
     auto& config_mgr = ConfigManager::instance();
     if (!config_mgr.load(config_path)) {
         LOG_WARN("Daemon", "Using default configuration");
         // Continue with defaults - not a critical failure
     }
     
     // Set log level from config
     const auto& config = config_mgr.get();
     switch (config.log_level) {
         case 0: Logger::set_level(LogLevel::DEBUG); break;
         case 1: Logger::set_level(LogLevel::INFO); break;
         case 2: Logger::set_level(LogLevel::WARN); break;
         case 3: Logger::set_level(LogLevel::ERROR); break;
         default: Logger::set_level(LogLevel::INFO); break;
     }
     
     // Setup signal handlers
     setup_signals();
     
     LOG_INFO("Daemon", "Initialization complete");
     // Always returns true - config loading failure is non-critical (uses defaults)
     return true;
 }
 
 int Daemon::run() {
     auto startup_start = std::chrono::steady_clock::now();
     LOG_INFO("Daemon", "Starting daemon");
     start_time_ = std::chrono::steady_clock::now();
     
     // Start all services
     if (!start_services()) {
         LOG_ERROR("Daemon", "Failed to start services");
         return 1;
     }
     
     running_ = true;
     
     // Notify systemd that we're ready
     notify_ready();
     
     // Log startup time with microsecond precision
     auto startup_end = std::chrono::steady_clock::now();
     auto elapsed_us = std::chrono::duration_cast<std::chrono::microseconds>(startup_end - startup_start);
     auto elapsed_ms = elapsed_us.count() / 1000.0;
     
     // Format: show as milliseconds with 3 decimal places, or microseconds if < 1ms
     std::string time_str;
     if (elapsed_ms >= 1.0) {
         char buf[32];
         snprintf(buf, sizeof(buf), "%.3f", elapsed_ms);
         time_str = std::string(buf) + "ms";
     } else {
         time_str = std::to_string(elapsed_us.count()) + "μs";
     }
     
     LOG_INFO("Daemon", "Startup completed in " + time_str);
     
     LOG_INFO("Daemon", "Daemon started successfully");
     
    // Main event loop
    while (!shutdown_requested_.load(std::memory_order_relaxed)) {
        event_loop();
    }
     
     LOG_INFO("Daemon", "Shutdown requested, stopping services");
     
     // Notify systemd we're stopping
     notify_stopping();
     
     // Stop all services
     stop_services();
     
     running_ = false;
     
     LOG_INFO("Daemon", "Daemon stopped");
     return 0;
 }
 
void Daemon::request_shutdown() {
    shutdown_requested_.store(true, std::memory_order_relaxed);
}
 
 void Daemon::register_service(std::unique_ptr<Service> service) {
     LOG_DEBUG("Daemon", "Registering service: " + std::string(service->name()));
     services_.push_back(std::move(service));
 }
 
 Config Daemon::config() const {
     return ConfigManager::instance().get();
 }
 
 std::chrono::seconds Daemon::uptime() const {
     auto now = std::chrono::steady_clock::now();
     return std::chrono::duration_cast<std::chrono::seconds>(now - start_time_);
 }
 
 void Daemon::notify_ready() {
     sd_notify(0, "READY=1\nSTATUS=Running");
     LOG_DEBUG("Daemon", "Notified systemd: READY");
 }
 
 void Daemon::notify_stopping() {
     sd_notify(0, "STOPPING=1\nSTATUS=Shutting down");
     LOG_DEBUG("Daemon", "Notified systemd: STOPPING");
 }
 
 void Daemon::notify_watchdog() {
     sd_notify(0, "WATCHDOG=1");
 }
 
bool Daemon::reload_config() {
    LOG_INFO("Daemon", "Reloading configuration");
    if (ConfigManager::instance().reload()) {
        // Reapply log level from config
        const auto& config = ConfigManager::instance().get();
        switch (config.log_level) {
            case 0: Logger::set_level(LogLevel::DEBUG); break;
            case 1: Logger::set_level(LogLevel::INFO); break;
            case 2: Logger::set_level(LogLevel::WARN); break;
            case 3: Logger::set_level(LogLevel::ERROR); break;
            default: Logger::set_level(LogLevel::INFO); break;
        }
        LOG_INFO("Daemon", "Configuration reloaded successfully");
        return true;
    }
    LOG_ERROR("Daemon", "Failed to reload configuration");
    return false;
}

void Daemon::reset() {
    // Reset all singleton state for test isolation
    // This ensures each test starts with a clean daemon state
    // WARNING: This function has no synchronization and should ONLY be called
    // when the daemon is stopped and no other threads are accessing services_.
    // For production builds, consider using #ifdef TESTING guards.
    
    // Stop any running services first
    stop_services();
    
    // Clear all registered services
    services_.clear();
    
    // Reset state flags
    shutdown_requested_.store(false, std::memory_order_relaxed);
    running_.store(false, std::memory_order_relaxed);
    
    // Reset start time
    start_time_ = std::chrono::steady_clock::time_point{};
    
    LOG_DEBUG("Daemon", "Daemon state reset for testing");
}

 void Daemon::setup_signals() {
     struct sigaction sa;
     sa.sa_handler = signal_handler;
     sigemptyset(&sa.sa_mask);
     sa.sa_flags = 0;
     
     sigaction(SIGTERM, &sa, nullptr);
     sigaction(SIGINT, &sa, nullptr);
     sigaction(SIGHUP, &sa, nullptr);
     
     // Ignore SIGPIPE (broken pipe from socket)
     signal(SIGPIPE, SIG_IGN);
     
     LOG_DEBUG("Daemon", "Signal handlers installed");
 }
 
 bool Daemon::start_services() {
     // Sort services by priority (higher first)
     std::sort(services_.begin(), services_.end(),
         [](const auto& a, const auto& b) {
             return a->priority() > b->priority();
         });
     
     for (auto& service : services_) {
         LOG_INFO("Daemon", "Starting service: " + std::string(service->name()));
         
         if (!service->start()) {
             LOG_ERROR("Daemon", "Failed to start service: " + std::string(service->name()));
             // Stop already started services
             stop_services();
             return false;
         }
         
         LOG_INFO("Daemon", "Service started: " + std::string(service->name()));
     }
     
     return true;
 }
 
 void Daemon::stop_services() {
     // Stop services in reverse order (lower priority first)
     for (auto it = services_.rbegin(); it != services_.rend(); ++it) {
         auto& service = *it;
         if (service->is_running()) {
             LOG_INFO("Daemon", "Stopping service: " + std::string(service->name()));
             service->stop();
             LOG_INFO("Daemon", "Service stopped: " + std::string(service->name()));
         }
     }
 }
 
 void Daemon::event_loop() {
     // Check signal flags set by the async-signal-safe handler
     // Perform the actual operations here in a normal thread context
     if (g_shutdown_requested) {
         g_shutdown_requested = 0;
         LOG_INFO("Daemon", "Received shutdown signal");
         request_shutdown();
         return;
     }
     
     if (g_reload_requested) {
         g_reload_requested = 0;
         LOG_INFO("Daemon", "Received SIGHUP, reloading configuration");
         reload_config();
     }
     
     // Check service health
     for (auto& service : services_) {
         if (service->is_running() && !service->is_healthy()) {
             LOG_WARN("Daemon", "Service unhealthy: " + std::string(service->name()));
         }
     }
     
     // Send watchdog keepalive
     notify_watchdog();
     
     // Sleep for a short interval
     std::this_thread::sleep_for(std::chrono::seconds(5));
 }
 
 } // namespace cortexd
 