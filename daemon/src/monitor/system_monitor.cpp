/**
 * @file system_monitor.cpp
 * @brief System monitor implementation
 */

#include "cortexd/monitor/system_monitor.h"
#include "cortexd/monitor/apt_monitor.h"
#include "cortexd/monitor/disk_monitor.h"
#include "cortexd/monitor/memory_monitor.h"
#include "cortexd/alerts/alert_manager.h"
#include "cortexd/llm/http_llm_client.h"
#include "cortexd/config.h"
#include "cortexd/logger.h"
#include <fstream>
#include <sstream>
#include <cstdlib>

namespace cortexd {

SystemMonitor::SystemMonitor(std::shared_ptr<AlertManager> alert_manager)
    : alert_manager_(std::move(alert_manager))
    , http_llm_client_(std::make_unique<HttpLLMClient>())
    , apt_monitor_(std::make_unique<AptMonitor>())
    , disk_monitor_(std::make_unique<DiskMonitor>())
    , memory_monitor_(std::make_unique<MemoryMonitor>()) {
    
    // Get interval from config
    const auto& config = ConfigManager::instance().get();
    check_interval_secs_.store(config.monitor_interval_sec, std::memory_order_relaxed);
    
    // Initialize HTTP LLM client from configuration
    initialize_http_llm_client();
}

void SystemMonitor::initialize_http_llm_client() {
    const auto& config = ConfigManager::instance().get();
    
    if (!config.enable_ai_alerts) {
        LOG_INFO("SystemMonitor", "AI alerts disabled in configuration");
        return;
    }
    
    LLMBackendType backend_type = LLMBackendType::NONE;
    std::string base_url;
    std::string api_key;
    
    if (config.llm_backend == "local") {
        backend_type = LLMBackendType::LOCAL;
        base_url = config.llm_api_url;
        LOG_INFO("SystemMonitor", "Configuring local llama-server at: " + base_url);
    } else if (config.llm_backend == "cloud_claude") {
        backend_type = LLMBackendType::CLOUD_CLAUDE;
        // Get API key from environment variable
        if (!config.llm_api_key_env.empty()) {
            const char* key = std::getenv(config.llm_api_key_env.c_str());
            if (key) api_key = key;
        }
        if (api_key.empty()) {
            const char* key = std::getenv("ANTHROPIC_API_KEY");
            if (key) api_key = key;
        }
        if (api_key.empty()) {
            LOG_WARN("SystemMonitor", "Claude API key not found, AI alerts disabled");
            return;
        }
        LOG_INFO("SystemMonitor", "Configuring Claude API for AI alerts");
    } else if (config.llm_backend == "cloud_openai") {
        backend_type = LLMBackendType::CLOUD_OPENAI;
        // Get API key from environment variable
        if (!config.llm_api_key_env.empty()) {
            const char* key = std::getenv(config.llm_api_key_env.c_str());
            if (key) api_key = key;
        }
        if (api_key.empty()) {
            const char* key = std::getenv("OPENAI_API_KEY");
            if (key) api_key = key;
        }
        if (api_key.empty()) {
            LOG_WARN("SystemMonitor", "OpenAI API key not found, AI alerts disabled");
            return;
        }
        LOG_INFO("SystemMonitor", "Configuring OpenAI API for AI alerts");
    } else if (config.llm_backend == "none" || config.llm_backend.empty()) {
        LOG_INFO("SystemMonitor", "No LLM backend configured, AI alerts disabled");
        return;
    } else {
        LOG_WARN("SystemMonitor", "Unknown LLM backend: " + config.llm_backend + ", AI alerts disabled");
        return;
    }
    
    http_llm_client_->configure(backend_type, base_url, api_key);
    
    if (http_llm_client_->is_configured()) {
        LOG_INFO("SystemMonitor", "AI-powered alerts enabled via HTTP LLM client");
    }
}

SystemMonitor::~SystemMonitor() {
    stop();
    
    // Join all AI analysis background threads for graceful shutdown
    std::lock_guard<std::mutex> lock(ai_threads_mutex_);
    for (auto& entry : ai_threads_) {
        if (entry.thread.joinable()) {
            entry.thread.join();
        }
    }
    ai_threads_.clear();
}

void SystemMonitor::cleanupFinishedAIThreads() {
    // Note: Caller must hold ai_threads_mutex_
    auto current_id = std::this_thread::get_id();
    
    auto it = ai_threads_.begin();
    while (it != ai_threads_.end()) {
        // Only clean up threads that have signaled completion
        if (it->done && it->done->load(std::memory_order_acquire)) {
            // Thread is finished, safe to join without blocking
            if (it->thread.joinable() && it->thread.get_id() != current_id) {
                it->thread.join();
            }
            it = ai_threads_.erase(it);
        } else if (!it->thread.joinable()) {
            // Thread already joined or default-constructed, remove it
            it = ai_threads_.erase(it);
        } else {
            ++it;
        }
    }
}

bool SystemMonitor::start() {
    if (running_) {
        return true;
    }
    
    running_ = true;
    monitor_thread_ = std::make_unique<std::thread>([this] { monitor_loop(); });
    
    LOG_INFO("SystemMonitor", "Started with " + 
             std::to_string(check_interval_secs_.load(std::memory_order_relaxed)) + "s interval");
    return true;
}

void SystemMonitor::stop() {
    if (!running_) {
        return;
    }
    
    running_ = false;
    
    if (monitor_thread_ && monitor_thread_->joinable()) {
        monitor_thread_->join();
    }
    
    LOG_INFO("SystemMonitor", "Stopped");
}

bool SystemMonitor::is_healthy() const {
    return running_.load();
}

HealthSnapshot SystemMonitor::get_snapshot() const {
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    return current_snapshot_;
}

std::vector<std::string> SystemMonitor::get_pending_updates() const {
    std::vector<std::string> updates;
    auto cached = apt_monitor_->get_cached_updates();
    for (const auto& update : cached) {
        updates.push_back(update.to_string());
    }
    return updates;
}

void SystemMonitor::trigger_check() {
    check_requested_ = true;
}

HealthSnapshot SystemMonitor::force_check() {
    LOG_DEBUG("SystemMonitor", "Running forced health check");
    run_checks();
    
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    return current_snapshot_;
}

void SystemMonitor::set_interval(std::chrono::seconds interval) {
    check_interval_secs_.store(interval.count(), std::memory_order_relaxed);
}

void SystemMonitor::monitor_loop() {
    LOG_DEBUG("SystemMonitor", "Monitor loop started");
    
    // Run initial check immediately
    run_checks();
    
    auto last_check = std::chrono::steady_clock::now();
    
    while (running_) {
        // Sleep in small increments to allow quick shutdown
        std::this_thread::sleep_for(std::chrono::seconds(1));
        
        auto now = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - last_check);
        
        // Check if interval elapsed or manual trigger
        auto interval_secs = check_interval_secs_.load(std::memory_order_relaxed);
        if (elapsed.count() >= interval_secs || check_requested_) {
            check_requested_ = false;
            run_checks();
            last_check = now;
        }
    }
    
    LOG_DEBUG("SystemMonitor", "Monitor loop ended");
}

void SystemMonitor::run_checks() {
    LOG_DEBUG("SystemMonitor", "Running health checks");
    
    try {
        // Get memory stats
        auto mem_stats = memory_monitor_->get_stats();
        
        // Get disk stats
        auto disk_stats = disk_monitor_->get_root_stats();
        
        // Get CPU usage using delta between successive reads
        double cpu_usage = 0.0;
        try {
            auto read_cpu_counters = []() -> CpuCounters {
                CpuCounters counters;
                std::ifstream stat("/proc/stat");
                if (stat.is_open()) {
                    std::string line;
                    std::getline(stat, line);
                    std::istringstream iss(line);
                    std::string cpu_label;
                    iss >> cpu_label >> counters.user >> counters.nice >> counters.system 
                        >> counters.idle >> counters.iowait;
                }
                return counters;
            };
            
            CpuCounters current = read_cpu_counters();
            
            // Lock cpu_mutex_ to protect access to prev_cpu_counters_ and cpu_counters_initialized_
            std::lock_guard<std::mutex> cpu_lock(cpu_mutex_);
            
            if (!cpu_counters_initialized_) {
                // First run: do a quick second reading after a short delay
                // to get an initial delta-based measurement
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                prev_cpu_counters_ = current;
                current = read_cpu_counters();
                cpu_counters_initialized_ = true;
            }
            
            // Calculate deltas from previous reading
            long delta_total = current.total() - prev_cpu_counters_.total();
            long delta_used = current.used() - prev_cpu_counters_.used();
            
            if (delta_total > 0) {
                cpu_usage = (static_cast<double>(delta_used) / delta_total) * 100.0;
            }
            
            // Store current counters for next iteration
            prev_cpu_counters_ = current;
        } catch (...) {
            // Ignore CPU errors
        }
        
        // Get APT updates (less frequently - only if enabled)
        const auto& config = ConfigManager::instance().get();
        int pending = 0;
        int security = 0;
        
        if (config.enable_apt_monitor) {
            // Only run apt check every 5 monitoring cycles (25 min by default)
            // Use atomic fetch_add for thread-safety between monitor_loop() and force_check()
            int current_count = apt_counter_.fetch_add(1, std::memory_order_relaxed);
            if (current_count % 5 == 0) {
                apt_monitor_->check_updates();
            }
            pending = apt_monitor_->pending_count();
            security = apt_monitor_->security_count();
        }
        
        // Update snapshot
        {
            std::lock_guard<std::mutex> lock(snapshot_mutex_);
            current_snapshot_.timestamp = Clock::now();
            current_snapshot_.cpu_usage_percent = cpu_usage;
            current_snapshot_.memory_usage_percent = mem_stats.usage_percent();
            current_snapshot_.memory_used_mb = mem_stats.used_mb();
            current_snapshot_.memory_total_mb = mem_stats.total_mb();
            current_snapshot_.disk_usage_percent = disk_stats.usage_percent();
            current_snapshot_.disk_used_gb = disk_stats.used_gb();
            current_snapshot_.disk_total_gb = disk_stats.total_gb();
            current_snapshot_.pending_updates = pending;
            current_snapshot_.security_updates = security;
            
            // Alert count from manager
            if (alert_manager_) {
                current_snapshot_.active_alerts = alert_manager_->count_active();
                current_snapshot_.critical_alerts = alert_manager_->count_by_severity(AlertSeverity::CRITICAL);
            }
        }
        
        // Check thresholds and create alerts using a local snapshot copy
        // (obtained while holding snapshot_mutex_ above)
        HealthSnapshot snapshot_copy;
        {
            std::lock_guard<std::mutex> lock(snapshot_mutex_);
            snapshot_copy = current_snapshot_;
        }
        check_thresholds(snapshot_copy);
        
        LOG_DEBUG("SystemMonitor", "Health check complete: CPU=" + 
                  std::to_string(cpu_usage) + "%, MEM=" + 
                  std::to_string(mem_stats.usage_percent()) + "%, DISK=" +
                  std::to_string(disk_stats.usage_percent()) + "%");
        
    } catch (const std::exception& e) {
        LOG_ERROR("SystemMonitor", "Error during health check: " + std::string(e.what()));
    }
}

void SystemMonitor::check_thresholds(const HealthSnapshot& snapshot) {
    if (!alert_manager_) {
        return;
    }
    
    const auto& config = ConfigManager::instance().get();
    
    // Check disk usage
    double disk_pct = snapshot.disk_usage_percent / 100.0;
    if (disk_pct >= config.disk_crit_threshold) {
        std::string context = "Disk usage: " + std::to_string(static_cast<int>(snapshot.disk_usage_percent)) + 
                             "%, Used: " + std::to_string(static_cast<int>(snapshot.disk_used_gb)) + 
                             "GB / " + std::to_string(static_cast<int>(snapshot.disk_total_gb)) + "GB total";
        create_smart_alert(
            AlertSeverity::CRITICAL,
            AlertType::DISK_USAGE,
            "Critical disk usage",
            "Disk usage is at " + std::to_string(static_cast<int>(snapshot.disk_usage_percent)) + 
            "% on root filesystem",
            context,
            {{"usage_percent", std::to_string(snapshot.disk_usage_percent)},
             {"used_gb", std::to_string(snapshot.disk_used_gb)},
             {"total_gb", std::to_string(snapshot.disk_total_gb)}}
        );
    } else if (disk_pct >= config.disk_warn_threshold) {
        std::string context = "Disk usage: " + std::to_string(static_cast<int>(snapshot.disk_usage_percent)) + 
                             "%, Used: " + std::to_string(static_cast<int>(snapshot.disk_used_gb)) + 
                             "GB / " + std::to_string(static_cast<int>(snapshot.disk_total_gb)) + "GB total";
        create_smart_alert(
            AlertSeverity::WARNING,
            AlertType::DISK_USAGE,
            "High disk usage",
            "Disk usage is at " + std::to_string(static_cast<int>(snapshot.disk_usage_percent)) + 
            "% on root filesystem",
            context,
            {{"usage_percent", std::to_string(snapshot.disk_usage_percent)},
             {"used_gb", std::to_string(snapshot.disk_used_gb)},
             {"total_gb", std::to_string(snapshot.disk_total_gb)}}
        );
    }
    
    // Check memory usage
    double mem_pct = snapshot.memory_usage_percent / 100.0;
    if (mem_pct >= config.mem_crit_threshold) {
        std::string context = "Memory usage: " + std::to_string(static_cast<int>(snapshot.memory_usage_percent)) + 
                             "%, Used: " + std::to_string(static_cast<int>(snapshot.memory_used_mb)) + 
                             "MB / " + std::to_string(static_cast<int>(snapshot.memory_total_mb)) + "MB total";
        create_smart_alert(
            AlertSeverity::CRITICAL,
            AlertType::MEMORY_USAGE,
            "Critical memory usage",
            "Memory usage is at " + std::to_string(static_cast<int>(snapshot.memory_usage_percent)) + "%",
            context,
            {{"usage_percent", std::to_string(snapshot.memory_usage_percent)},
             {"used_mb", std::to_string(snapshot.memory_used_mb)},
             {"total_mb", std::to_string(snapshot.memory_total_mb)}}
        );
    } else if (mem_pct >= config.mem_warn_threshold) {
        std::string context = "Memory usage: " + std::to_string(static_cast<int>(snapshot.memory_usage_percent)) + 
                             "%, Used: " + std::to_string(static_cast<int>(snapshot.memory_used_mb)) + 
                             "MB / " + std::to_string(static_cast<int>(snapshot.memory_total_mb)) + "MB total";
        create_smart_alert(
            AlertSeverity::WARNING,
            AlertType::MEMORY_USAGE,
            "High memory usage",
            "Memory usage is at " + std::to_string(static_cast<int>(snapshot.memory_usage_percent)) + "%",
            context,
            {{"usage_percent", std::to_string(snapshot.memory_usage_percent)},
             {"used_mb", std::to_string(snapshot.memory_used_mb)},
             {"total_mb", std::to_string(snapshot.memory_total_mb)}}
        );
    }
    
    // Check for security updates
    if (snapshot.security_updates > 0) {
        // Get the actual update list for AI context
        auto updates = apt_monitor_->get_cached_updates();
        std::string update_list;
        int count = 0;
        for (const auto& update : updates) {
            if (update.is_security && count < 5) {  // Limit to first 5 for prompt
                update_list += "- " + update.to_string() + "\n";
                count++;
            }
        }
        if (count < snapshot.security_updates) {
            update_list += "... and " + std::to_string(snapshot.security_updates - count) + " more\n";
        }
        
        std::string context = std::to_string(snapshot.security_updates) + 
                             " security updates available:\n" + update_list;
        create_smart_alert(
            AlertSeverity::WARNING,
            AlertType::SECURITY_UPDATE,
            "Security updates available",
            std::to_string(snapshot.security_updates) + " security update(s) available",
            context,
            {{"count", std::to_string(snapshot.security_updates)}}
        );
    }
}

std::string SystemMonitor::generate_ai_alert(AlertType alert_type, const std::string& context) {
    const auto& config = ConfigManager::instance().get();
    
    // Check if AI alerts are enabled and HTTP LLM client is configured
    if (!config.enable_ai_alerts || !http_llm_client_ || !http_llm_client_->is_configured()) {
        return "";
    }
    
    // Build simple, direct prompts based on alert type
    std::string prompt;
    
    switch (alert_type) {
        case AlertType::DISK_USAGE:
            prompt = context + "\n\nHow can I free up disk space on this Linux system? Give 2 specific commands or actions.";
            break;
            
        case AlertType::MEMORY_USAGE:
            prompt = context + "\n\nHow can I reduce memory usage on this Linux system? Give 2 specific commands or actions.";
            break;
            
        case AlertType::SECURITY_UPDATE:
            prompt = context + "\n\nShould I install these security updates now? Give a brief recommendation.";
            break;
            
        case AlertType::CVE_FOUND:
            prompt = context + "\n\nHow serious is this vulnerability and what should I do? Give a brief recommendation.";
            break;
            
        default:
            prompt = context + "\n\nWhat action should I take for this alert? Give a brief recommendation.";
            break;
    }
    
    LOG_DEBUG("SystemMonitor", "Generating AI alert analysis via HTTP LLM client...");
    
    // Use HTTP LLM client for inference
    auto result = http_llm_client_->generate(prompt, 150, 0.3f);
    
    if (result.success && !result.output.empty()) {
        LOG_DEBUG("SystemMonitor", "AI analysis generated successfully");
        return result.output;
    }
    
    if (!result.success) {
        LOG_WARN("SystemMonitor", "AI analysis failed: " + result.error);
    }
    
    return "";
}

void SystemMonitor::create_smart_alert(AlertSeverity severity, AlertType type,
                                       const std::string& title, const std::string& basic_message,
                                       const std::string& ai_context,
                                       const std::map<std::string, std::string>& metadata) {
    // Create the alert immediately with the basic message (non-blocking)
    auto metadata_copy = metadata;
    metadata_copy["ai_enhanced"] = "pending";
    
    std::string alert_id = alert_manager_->create(severity, type, title, basic_message, metadata_copy);
    
    // Skip AI analysis if HTTP LLM client not available or alert creation failed
    if (alert_id.empty() || !http_llm_client_ || !http_llm_client_->is_configured()) {
        return;
    }
    
    // Capture a weak_ptr to avoid use-after-free if AlertManager is destroyed
    std::weak_ptr<AlertManager> weak_alert_mgr = alert_manager_;
    
    // Capture pointer to running_ atomic for safe liveness check in thread
    // This is safe because running_ outlives all threads (joined in destructor)
    std::atomic<bool>* running_ptr = &running_;
    
    // Capture this pointer for calling generate_ai_alert
    // Safe because destructor joins all threads before destruction completes
    SystemMonitor* self = this;
    
    // Create a shared "done" flag for non-blocking cleanup
    auto done_flag = std::make_shared<std::atomic<bool>>(false);
    
    // Create thread for AI analysis (will be joined in destructor)
    std::thread ai_thread([weak_alert_mgr, type, ai_context, title, alert_id, severity, 
                           running_ptr, self, done_flag]() {
        // Ensure done flag is set when thread exits (success, exception, or early return)
        struct DoneGuard {
            std::shared_ptr<std::atomic<bool>> flag;
            ~DoneGuard() { flag->store(true, std::memory_order_release); }
        } guard{done_flag};
        
        try {
            LOG_DEBUG("SystemMonitor", "Generating AI alert analysis in background...");
            
            // Check if SystemMonitor is still running before accessing llm_engine_
            if (!running_ptr->load()) {
                LOG_DEBUG("SystemMonitor", "SystemMonitor stopping, skipping AI analysis");
                return;
            }
            
            // Lock the weak_ptr to get a shared_ptr - if this fails, the AlertManager
            // has been destroyed and we should abort
            auto alert_mgr = weak_alert_mgr.lock();
            if (!alert_mgr) {
                LOG_DEBUG("SystemMonitor", "AlertManager no longer available, skipping AI analysis");
                return;
            }
            
            // Generate AI analysis using the LLM (generate_ai_alert has internal null checks)
            std::string ai_analysis = self->generate_ai_alert(type, ai_context);
            
            // Create a secondary alert with AI analysis results
            std::map<std::string, std::string> ai_metadata;
            ai_metadata["parent_alert_id"] = alert_id;
            ai_metadata["ai_enhanced"] = "true";
            ai_metadata["analysis_context"] = ai_context;
            
            // Build the AI message - include actual analysis if available
            std::string ai_alert_title = "AI analysis: " + title;
            std::string ai_message;
            if (!ai_analysis.empty()) {
                ai_message = "AI-generated analysis:\n\n" + ai_analysis + 
                            "\n\n---\nParent alert: " + alert_id.substr(0, 8);
                ai_metadata["ai_analysis"] = ai_analysis;
            } else {
                ai_message = "Automated analysis for alert: " + alert_id.substr(0, 8) + 
                            "\n\nContext analyzed:\n" + ai_context +
                            "\n\n(AI analysis unavailable or returned empty)";
                LOG_WARN("SystemMonitor", "AI analysis returned empty for alert: " + alert_id.substr(0, 8));
            }
            
            std::string ai_alert_id = alert_mgr->create(
                AlertSeverity::INFO,
                AlertType::AI_ANALYSIS,
                ai_alert_title,
                ai_message,
                ai_metadata
            );
            
            if (!ai_alert_id.empty()) {
                LOG_DEBUG("SystemMonitor", "Created AI analysis alert: " + ai_alert_id.substr(0, 8) + 
                         " for parent: " + alert_id.substr(0, 8));
            } else {
                LOG_WARN("SystemMonitor", "Failed to create AI analysis alert for: " + alert_id.substr(0, 8));
            }
        } catch (const std::exception& e) {
            LOG_ERROR("SystemMonitor", "Exception in AI analysis thread: " + std::string(e.what()));
        } catch (...) {
            LOG_ERROR("SystemMonitor", "Unknown exception in AI analysis thread");
        }
    });
    
    // Clean up finished threads before adding new one to avoid unbounded accumulation
    {
        std::lock_guard<std::mutex> lock(ai_threads_mutex_);
        cleanupFinishedAIThreads();
        
        // Store the new thread with its done flag for graceful shutdown
        ai_threads_.push_back(AIThreadEntry{std::move(ai_thread), done_flag});
    }
}

} // namespace cortexd

