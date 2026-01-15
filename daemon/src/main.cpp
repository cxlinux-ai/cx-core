/**
 * @file main.cpp
 * @brief cortexd daemon entry point
 */

#include "cortexd/core/daemon.h"
#include "cortexd/ipc/server.h"
#include "cortexd/ipc/handlers.h"
#include "cortexd/logger.h"
#include "cortexd/config.h"
#include "cortexd/common.h"
#include <iostream>
#include <getopt.h>
 
 using namespace cortexd;
 
 void print_version() {
     std::cout << NAME << " " << VERSION << std::endl;
 }
 
 void print_usage(const char* prog) {
     std::cout << "Usage: " << prog << " [options]\n\n"
               << "Cortex AI Package Manager Daemon\n\n"
               << "Options:\n"
               << "  -c, --config PATH    Configuration file path\n"
               << "                       (default: " << DEFAULT_CONFIG_PATH << ")\n"
               << "  -v, --verbose        Enable debug logging\n"
               << "  -f, --foreground     Run in foreground (don't daemonize)\n"
               << "  -h, --help           Show this help message\n"
               << "  --version            Show version information\n"
               << "\n"
               << "Examples:\n"
               << "  " << prog << "                         Start with default config\n"
               << "  " << prog << " -c /etc/cortex/custom.yaml\n"
               << "  " << prog << " -v                      Start with debug logging\n"
               << "\n"
               << "systemd integration:\n"
               << "  systemctl start cortexd       Start the daemon\n"
               << "  systemctl stop cortexd        Stop the daemon\n"
               << "  systemctl status cortexd      Check status\n"
               << "  journalctl -u cortexd -f      View logs\n"
               << std::endl;
 }
 
 int main(int argc, char* argv[]) {
     std::string config_path = DEFAULT_CONFIG_PATH;
     bool verbose = false;
     bool foreground = false;
     
     // Parse command line options
     static struct option long_options[] = {
         {"config",     required_argument, nullptr, 'c'},
         {"verbose",    no_argument,       nullptr, 'v'},
         {"foreground", no_argument,       nullptr, 'f'},
         {"help",       no_argument,       nullptr, 'h'},
         {"version",    no_argument,       nullptr, 'V'},
         {nullptr, 0, nullptr, 0}
     };
     
    int opt;
    while ((opt = getopt_long(argc, argv, "c:vfhV", long_options, nullptr)) != -1) {
         switch (opt) {
             case 'c':
                 config_path = optarg;
                 break;
             case 'v':
                 verbose = true;
                 break;
             case 'f':
                 foreground = true;
                 break;
             case 'h':
                 print_usage(argv[0]);
                 return 0;
             case 'V':
                 print_version();
                 return 0;
             default:
                 print_usage(argv[0]);
                 return 1;
         }
     }
     
     // Initialize logging
     // Use journald unless in foreground mode
     Logger::init(
         verbose ? LogLevel::DEBUG : LogLevel::INFO,
         !foreground  // Use journald when not in foreground
     );
     
     LOG_INFO("main", "cortexd starting - version " + std::string(VERSION));
     
     // Get daemon instance
     auto& daemon = Daemon::instance();
     
     // Initialize daemon with config
     if (!daemon.initialize(config_path)) {
         LOG_ERROR("main", "Failed to initialize daemon");
         return 1;
     }
     
     // Get configuration
     const auto& config = ConfigManager::instance().get();
     
     // Create IPC server
     auto ipc_server = std::make_unique<IPCServer>(
         config.socket_path,
         config.max_requests_per_sec
     );
     
     // Register IPC handlers
     Handlers::register_all(*ipc_server);
     
     // Register services with daemon
     daemon.register_service(std::move(ipc_server));
     
     // Run daemon (blocks until shutdown)
     int exit_code = daemon.run();
     
     LOG_INFO("main", "cortexd shutdown complete");
     Logger::shutdown();
     
     return exit_code;
 }
 