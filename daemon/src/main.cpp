#include <iostream>
#include <signal.h>
#include <syslog.h>
#include <unistd.h>
#include <memory>
#include <thread>
#include <chrono>
#include <systemd/sd-daemon.h>
#include "cortexd_common.h"
#include "socket_server.h"
#include "system_monitor.h"
#include "alert_manager.h"
#include "daemon_config.h"
#include "logging.h"
#include "llm_wrapper.h"

using namespace cortex::daemon;

// Global pointers for signal handlers
std::unique_ptr<SocketServer> g_socket_server;
std::unique_ptr<SystemMonitor> g_system_monitor;
std::unique_ptr<LLMWrapper> g_llm_wrapper;
static std::atomic<bool> g_shutdown_requested(false);

// Signal handler
void signal_handler(int sig) {
    if (sig == SIGTERM || sig == SIGINT) {
        Logger::info("main", "Received shutdown signal");
        g_shutdown_requested = true;
    }
}

// Setup signal handlers
void setup_signals() {
    struct sigaction sa;
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;

    sigaction(SIGTERM, &sa, nullptr);
    sigaction(SIGINT, &sa, nullptr);
    sigaction(SIGPIPE, &sa, nullptr); // Ignore broken pipes
}

int main(int argc, char* argv[]) {
    (void)argc;  // unused
    (void)argv;  // unused
    // Initialize logging
    Logger::init(true);
    Logger::info("main", "cortexd starting - version " + std::string(DAEMON_VERSION));

    // Load configuration
    auto& config_mgr = DaemonConfigManager::instance();
    if (!config_mgr.load_config()) {
        Logger::warn("main", "Using default configuration");
    }

    const auto& config = config_mgr.get_config();
    Logger::set_level(static_cast<LogLevel>(config.log_level));

    // Setup signal handlers
    setup_signals();

    // Create and start socket server
    g_socket_server = std::make_unique<SocketServer>(config.socket_path);
    if (!g_socket_server->start()) {
        Logger::error("main", "Failed to start socket server");
        return 1;
    }
    Logger::info("main", "Socket server started on " + config.socket_path);

    // Create and start system monitor
    g_system_monitor = std::make_unique<SystemMonitorImpl>();
    g_system_monitor->start_monitoring();
    Logger::info("main", "System monitoring started");

    // Initialize LLM wrapper
    g_llm_wrapper = std::make_unique<LlamaWrapper>();
    
    // Try to load model if path is configured
    if (!config.model_path.empty() && config.model_path != "~/.cortex/models/default.gguf") {
        // Expand ~ to home directory
        std::string model_path = config.model_path;
        if (model_path[0] == '~') {
            const char* home = getenv("HOME");
            if (home) {
                model_path = std::string(home) + model_path.substr(1);
            }
        }
        
        Logger::info("main", "Attempting to load model from: " + model_path);
        if (g_llm_wrapper->load_model(model_path)) {
            Logger::info("main", "LLM model loaded successfully");
            // Notify system monitor that LLM is loaded
            if (g_system_monitor) {
                g_system_monitor->set_llm_loaded(true);
            }
        } else {
            Logger::warn("main", "Failed to load LLM model (daemon will continue without LLM support)");
        }
    } else {
        Logger::info("main", "No model path configured, skipping LLM initialization");
    }

    // Notify systemd that we're ready
    sd_notify(0, "READY=1\nSTATUS=Running normally");

    // Main event loop
    std::chrono::seconds check_interval(5);
    while (!g_shutdown_requested) {
        std::this_thread::sleep_for(check_interval);

        // Perform periodic health checks
        try {
            auto health = g_system_monitor->get_health_snapshot();
            Logger::debug("main", "Health check: CPU=" + std::to_string(health.cpu_usage) +
                                 "%, Memory=" + std::to_string(health.memory_usage) + "%");
        } catch (const std::exception& e) {
            Logger::error("main", "Health check failed: " + std::string(e.what()));
        }
    }

    // Graceful shutdown
    Logger::info("main", "Shutting down gracefully");

    sd_notify(0, "STOPPING=1\nSTATUS=Shutting down");

    // Stop monitoring
    if (g_system_monitor) {
        g_system_monitor->stop_monitoring();
    }

    // Unload LLM
    if (g_llm_wrapper) {
        g_llm_wrapper->unload_model();
    }

    // Stop socket server
    if (g_socket_server) {
        g_socket_server->stop();
    }

    Logger::info("main", "cortexd shutdown complete");
    Logger::shutdown();

    return 0;
}
