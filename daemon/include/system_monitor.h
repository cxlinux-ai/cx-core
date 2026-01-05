#pragma once

#include <string>
#include <vector>
#include <memory>
#include <chrono>
#include <atomic>
#include <thread>
#include <mutex>
#include "cortexd_common.h"

namespace cortex {
namespace daemon {

// System monitor interface
class SystemMonitor {
public:
    virtual ~SystemMonitor() = default;

    // Run monitoring checks
    virtual void run_checks() = 0;

    // Get health snapshot
    virtual HealthSnapshot get_health_snapshot() = 0;

    // Start background monitoring loop
    virtual void start_monitoring() = 0;

    // Stop monitoring
    virtual void stop_monitoring() = 0;

    // Check APT updates
    virtual std::vector<std::string> check_apt_updates() = 0;

    // Check disk usage
    virtual double get_disk_usage_percent() = 0;

    // Check memory usage
    virtual double get_memory_usage_percent() = 0;

    // Check CVEs
    virtual std::vector<std::string> scan_cves() = 0;

    // Check dependency conflicts
    virtual std::vector<std::string> check_dependencies() = 0;
    
    // Set LLM loaded status
    virtual void set_llm_loaded(bool loaded) = 0;
};

// Concrete implementation
class SystemMonitorImpl : public SystemMonitor {
public:
    SystemMonitorImpl();
    ~SystemMonitorImpl();

    void run_checks() override;
    HealthSnapshot get_health_snapshot() override;
    void start_monitoring() override;
    void stop_monitoring() override;

    std::vector<std::string> check_apt_updates() override;
    double get_disk_usage_percent() override;
    double get_memory_usage_percent() override;
    std::vector<std::string> scan_cves() override;
    std::vector<std::string> check_dependencies() override;
    void set_llm_loaded(bool loaded) override;

private:
    std::atomic<bool> monitoring_active_;
    std::unique_ptr<std::thread> monitor_thread_;
    HealthSnapshot last_snapshot_;
    std::mutex snapshot_mutex_;

    void monitoring_loop();
    double get_cpu_usage_percent();
    int count_processes();
    int count_open_files();
};

} // namespace daemon
} // namespace cortex
