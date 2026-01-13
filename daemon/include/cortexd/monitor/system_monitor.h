/**
 * @file system_monitor.h
 * @brief Main system monitoring orchestrator
 */

#pragma once

#include "cortexd/core/service.h"
#include "cortexd/common.h"
#include <memory>
#include <thread>
#include <atomic>
#include <mutex>
#include <vector>
#include <chrono>
#include <map>
#include <string>

namespace cortexd {

// Forward declarations
class AptMonitor;
class DiskMonitor;
class MemoryMonitor;
class CVEScanner;
class DependencyChecker;
class AlertManager;
class HttpLLMClient;

/**
 * @brief System monitoring service
 * 
 * Orchestrates all monitoring subsystems and periodically checks
 * system health, creating alerts when thresholds are exceeded.
 */
/**
 * @brief CPU counter values for delta-based usage calculation
 */
struct CpuCounters {
    long user = 0;
    long nice = 0;
    long system = 0;
    long idle = 0;
    long iowait = 0;
    
    long total() const { return user + nice + system + idle + iowait; }
    long used() const { return user + nice + system; }
};

class SystemMonitor : public Service {
public:
    /**
     * @brief Construct with optional alert manager
     * @param alert_manager Shared alert manager (can be nullptr)
     * 
     * AI-powered alerts use HttpLLMClient which is configured automatically
     * from daemon config (supports local llama-server or cloud APIs).
     */
    explicit SystemMonitor(std::shared_ptr<AlertManager> alert_manager = nullptr);
    ~SystemMonitor() override;
    
    // Service interface
    bool start() override;
    void stop() override;
    const char* name() const override { return "SystemMonitor"; }
    int priority() const override { return 50; }
    bool is_running() const override { return running_.load(); }
    bool is_healthy() const override;
    
    /**
     * @brief Get current health snapshot
     */
    HealthSnapshot get_snapshot() const;
    
    /**
     * @brief Get list of pending package updates
     */
    std::vector<std::string> get_pending_updates() const;
    
    /**
     * @brief Trigger immediate health check (async)
     */
    void trigger_check();
    
    /**
     * @brief Force synchronous health check and return snapshot
     * @return Fresh health snapshot
     */
    HealthSnapshot force_check();
    
    /**
     * @brief Set check interval
     */
    void set_interval(std::chrono::seconds interval);
    
    /**
     * @brief Initialize HTTP LLM client from configuration
     */
    void initialize_http_llm_client();
    
private:
    std::shared_ptr<AlertManager> alert_manager_;
    std::unique_ptr<HttpLLMClient> http_llm_client_;  // HTTP client for LLM API calls
    
    std::unique_ptr<AptMonitor> apt_monitor_;
    std::unique_ptr<DiskMonitor> disk_monitor_;
    std::unique_ptr<MemoryMonitor> memory_monitor_;
    
    std::unique_ptr<std::thread> monitor_thread_;
    std::atomic<bool> running_{false};
    std::atomic<bool> check_requested_{false};
    
    mutable std::mutex snapshot_mutex_;
    HealthSnapshot current_snapshot_;
    
    std::atomic<int64_t> check_interval_secs_{300};  // 5 minutes (atomic for thread-safe access)
    
    // Thread-safe APT check counter (replaces static local)
    std::atomic<int> apt_counter_{0};
    
    // CPU usage delta calculation state (protected by cpu_mutex_)
    mutable std::mutex cpu_mutex_;
    CpuCounters prev_cpu_counters_;
    bool cpu_counters_initialized_{false};
    
    // AI analysis background threads (for graceful shutdown)
    // Each thread is paired with a "done" flag to enable non-blocking cleanup
    struct AIThreadEntry {
        std::thread thread;
        std::shared_ptr<std::atomic<bool>> done;
    };
    mutable std::mutex ai_threads_mutex_;
    std::vector<AIThreadEntry> ai_threads_;
    
    /**
     * @brief Clean up finished AI threads to avoid unbounded accumulation
     * @note Must be called with ai_threads_mutex_ held
     */
    void cleanupFinishedAIThreads();
    
    /**
     * @brief Main monitoring loop
     */
    void monitor_loop();
    
    /**
     * @brief Run all health checks
     */
    void run_checks();
    
    /**
     * @brief Check thresholds and create alerts
     * @param snapshot Copy of current health snapshot to check
     */
    void check_thresholds(const HealthSnapshot& snapshot);
    
    /**
     * @brief Generate AI-powered alert message using LLM
     * @param alert_type Type of alert
     * @param context Context information for the LLM
     * @return AI-generated message or empty string if unavailable
     */
    std::string generate_ai_alert(AlertType alert_type, const std::string& context);
    
    /**
     * @brief Create alert with optional AI enhancement
     */
    void create_smart_alert(AlertSeverity severity, AlertType type,
                           const std::string& title, const std::string& basic_message,
                           const std::string& ai_context,
                           const std::map<std::string, std::string>& metadata);
};

} // namespace cortexd

