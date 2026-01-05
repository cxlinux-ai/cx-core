#include "system_monitor.h"
#include "logging.h"
#include <fstream>
#include <sstream>
#include <thread>
#include <chrono>
#include <regex>
#include <sys/statvfs.h>

namespace cortex {
namespace daemon {

SystemMonitorImpl::SystemMonitorImpl() : monitoring_active_(false) {
    Logger::info("SystemMonitor", "Initialized");
}

SystemMonitorImpl::~SystemMonitorImpl() {
    stop_monitoring();
}

void SystemMonitorImpl::start_monitoring() {
    if (monitoring_active_) {
        return;
    }

    monitoring_active_ = true;
    monitor_thread_ = std::make_unique<std::thread>([this] { monitoring_loop(); });
    Logger::info("SystemMonitor", "Monitoring started");
}

void SystemMonitorImpl::stop_monitoring() {
    if (!monitoring_active_) {
        return;
    }

    monitoring_active_ = false;
    if (monitor_thread_ && monitor_thread_->joinable()) {
        monitor_thread_->join();
    }

    Logger::info("SystemMonitor", "Monitoring stopped");
}

void SystemMonitorImpl::monitoring_loop() {
    // Run checks immediately
    try {
        run_checks();
    } catch (const std::exception& e) {
        Logger::error("SystemMonitor", "Initial monitoring failed: " + std::string(e.what()));
    }

    while (monitoring_active_) {
        try {
            // Sleep for monitoring interval first
            std::this_thread::sleep_for(std::chrono::seconds(MONITORING_INTERVAL_SECONDS));
            run_checks();
        } catch (const std::exception& e) {
            Logger::error("SystemMonitor", "Monitoring loop error: " + std::string(e.what()));
        }
    }
}

void SystemMonitorImpl::run_checks() {
    std::lock_guard<std::mutex> lock(snapshot_mutex_);

    last_snapshot_.timestamp = std::chrono::system_clock::now();
    last_snapshot_.cpu_usage = get_cpu_usage_percent();
    last_snapshot_.memory_usage = get_memory_usage_percent();
    last_snapshot_.disk_usage = get_disk_usage_percent();
    last_snapshot_.active_processes = count_processes();
    last_snapshot_.open_files = count_open_files();
    
    last_snapshot_.llm_loaded = false; // Set by LLM wrapper when model loaded
    last_snapshot_.inference_queue_size = 0; // Set by inference queue
    last_snapshot_.alerts_count = 0; // Set by alert manager
}

HealthSnapshot SystemMonitorImpl::get_health_snapshot() {
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    return last_snapshot_;
}

std::vector<std::string> SystemMonitorImpl::check_apt_updates() {
    std::vector<std::string> updates;
    // TODO: implement apt update checking
    Logger::debug("SystemMonitor", "Checked APT updates");
    return updates;
}

double SystemMonitorImpl::get_disk_usage_percent() {
    try {
        // Read disk usage from /proc/mounts and calculate for root filesystem
        std::ifstream mounts("/proc/mounts");
        if (!mounts.is_open()) {
            return 0.0;
        }

        // Find root filesystem mount
        std::string line;
        while (std::getline(mounts, line)) {
            std::istringstream iss(line);
            std::string device, mountpoint, fstype;
            iss >> device >> mountpoint >> fstype;
            
            if (mountpoint == "/") {
                // For root filesystem, use statvfs
                struct statvfs stat;
                if (statvfs("/", &stat) == 0) {
                    unsigned long long total = stat.f_blocks * stat.f_frsize;
                    unsigned long long available = stat.f_bavail * stat.f_frsize;
                    unsigned long long used = total - available;
                    
                    if (total > 0) {
                        return (static_cast<double>(used) / static_cast<double>(total)) * 100.0;
                    }
                }
                break;
            }
        }

        return 0.0;
    } catch (const std::exception& e) {
        Logger::error("SystemMonitor", "Failed to get disk usage: " + std::string(e.what()));
        return 0.0;
    }
}

double SystemMonitorImpl::get_memory_usage_percent() {
    try {
        std::ifstream meminfo("/proc/meminfo");
        if (!meminfo.is_open()) {
            return 0.0;
        }

        long mem_total = 0, mem_available = 0;
        std::string line;

        while (std::getline(meminfo, line)) {
            if (line.find("MemTotal:") == 0) {
                mem_total = std::stol(line.substr(9));
            } else if (line.find("MemAvailable:") == 0) {
                mem_available = std::stol(line.substr(13));
            }
        }

        if (mem_total == 0) return 0.0;

        long mem_used = mem_total - mem_available;
        return (static_cast<double>(mem_used) / static_cast<double>(mem_total)) * 100.0;
    } catch (const std::exception& e) {
        Logger::error("SystemMonitor", "Failed to get memory usage: " + std::string(e.what()));
        return 0.0;
    }
}

std::vector<std::string> SystemMonitorImpl::scan_cves() {
    std::vector<std::string> cves;
    // TODO: implement CVE scanning with local database
    Logger::debug("SystemMonitor", "Scanned for CVEs");
    return cves;
}

std::vector<std::string> SystemMonitorImpl::check_dependencies() {
    std::vector<std::string> conflicts;
    // TODO: implement dependency conflict checking
    Logger::debug("SystemMonitor", "Checked for dependency conflicts");
    return conflicts;
}

double SystemMonitorImpl::get_cpu_usage_percent() {
    try {
        std::ifstream stat("/proc/stat");
        if (!stat.is_open()) {
            return 0.0;
        }

        std::string line;
        std::getline(stat, line);  // First line contains aggregate CPU stats

        // Format: cpu user nice system idle iowait irq softirq steal guest guest_nice
        std::istringstream iss(line);
        std::string cpu_label;
        long user, nice, system, idle, iowait;
        
        iss >> cpu_label >> user >> nice >> system >> idle >> iowait;

        long total = user + nice + system + idle + iowait;
        long used = user + nice + system;

        if (total == 0) return 0.0;

        return (static_cast<double>(used) / static_cast<double>(total)) * 100.0;
    } catch (const std::exception& e) {
        Logger::error("SystemMonitor", "Failed to get CPU usage: " + std::string(e.what()));
        return 0.0;
    }
}

int SystemMonitorImpl::count_processes() {
    try {
        std::ifstream stat("/proc/stat");
        if (!stat.is_open()) {
            return 0;
        }

        int process_count = 0;
        std::string line;

        while (std::getline(stat, line)) {
            if (line.find("processes") == 0) {
                std::istringstream iss(line);
                std::string label;
                iss >> label >> process_count;
                break;
            }
        }

        return process_count;
    } catch (const std::exception& e) {
        Logger::error("SystemMonitor", "Failed to count processes: " + std::string(e.what()));
        return 0;
    }
}

int SystemMonitorImpl::count_open_files() {
    try {
        // Count files in /proc/self/fd (open file descriptors)
        int count = 0;
        std::string fd_path = "/proc/self/fd";
        
        // Use a simple approach: count entries in fd directory
        // This is an estimate based on max allowed file descriptors
        std::ifstream limits("/proc/sys/fs/file-max");
        if (limits.is_open()) {
            // For now, return a reasonable estimate based on system limits
            return 0;  // Placeholder - would need dirent.h to properly count
        }

        return count;
    } catch (const std::exception& e) {
        Logger::error("SystemMonitor", "Failed to count open files: " + std::string(e.what()));
        return 0;
    }
}

void SystemMonitorImpl::set_llm_loaded(bool loaded) {
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    last_snapshot_.llm_loaded = loaded;
}

} // namespace daemon
} // namespace cortex
