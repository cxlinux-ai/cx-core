/**
 * @file config.h
 * @brief Configuration management with YAML support
 */

#pragma once

#include "cortexd/common.h"
#include <string>
#include <chrono>
#include <optional>
#include <functional>
#include <mutex>
#include <vector>

namespace cortexd {

/**
 * @brief Daemon configuration structure
 */
struct Config {
    // Socket configuration
    std::string socket_path = DEFAULT_SOCKET_PATH;
    int socket_backlog = SOCKET_BACKLOG;
    int socket_timeout_ms = SOCKET_TIMEOUT_MS;
    
    // LLM configuration
    std::string llm_backend = "none";  // "none", "local", "cloud_claude", "cloud_openai"
    std::string llm_api_url = "http://127.0.0.1:8085";  // URL for local llama-server
    std::string llm_api_key_env = "";  // Environment variable for API key (cloud backends)
    
    // Legacy embedded LLM settings (deprecated)
    std::string model_path;
    int llm_context_length = 2048;
    int llm_threads = 4;
    int llm_batch_size = 512;
    bool llm_lazy_load = true;  // Load model on first request
    bool llm_mmap = true;       // Use memory mapping for model
    
    // Monitoring configuration
    int monitor_interval_sec = DEFAULT_MONITOR_INTERVAL_SEC;
    bool enable_apt_monitor = true;
    bool enable_cve_scanner = true;
    bool enable_dependency_checker = true;
    
    // Threshold configuration
    double disk_warn_threshold = DEFAULT_DISK_WARN_THRESHOLD;
    double disk_crit_threshold = DEFAULT_DISK_CRIT_THRESHOLD;
    double mem_warn_threshold = DEFAULT_MEM_WARN_THRESHOLD;
    double mem_crit_threshold = DEFAULT_MEM_CRIT_THRESHOLD;
    
    // Alert configuration
    std::string alert_db_path = DEFAULT_ALERT_DB;
    int alert_retention_hours = ALERT_RETENTION_HOURS;
    bool enable_ai_alerts = true;  // Use LLM to generate intelligent alert messages
    
    // Rate limiting
    int max_requests_per_sec = MAX_REQUESTS_PER_SECOND;
    int max_inference_queue = MAX_INFERENCE_QUEUE_SIZE;
    
    // Logging
    int log_level = 1;  // INFO by default (0=DEBUG, 1=INFO, 2=WARN, 3=ERROR)
    
    /**
     * @brief Load configuration from YAML file
     * @param path Path to YAML configuration file
     * @return Config if successful, std::nullopt on error
     */
    static std::optional<Config> load(const std::string& path);
    
    /**
     * @brief Save configuration to YAML file
     * @param path Path to save configuration
     * @return true if successful
     */
    bool save(const std::string& path) const;
    
    /**
     * @brief Expand all paths (~ -> home directory)
     */
    void expand_paths();
    
    /**
     * @brief Validate configuration values
     * @return Error message if invalid, empty string if valid
     */
    std::string validate() const;
    
    /**
     * @brief Get default configuration
     */
    static Config defaults();
};

/**
 * @brief Configuration manager singleton
 */
class ConfigManager {
public:
    /**
     * @brief Get singleton instance
     */
    static ConfigManager& instance();
    
    /**
     * @brief Load configuration from file
     * @param path Path to configuration file
     * @return true if successful
     */
    bool load(const std::string& path);
    
    /**
     * @brief Reload configuration from previously loaded path
     * @return true if successful
     */
    bool reload();
    
    /**
     * @brief Get current configuration (returns copy for thread safety)
     */
    Config get() const;
    
    /**
     * @brief Get configuration file path
     */
    const std::string& config_path() const { return config_path_; }
    
    /**
     * @brief Register callback for configuration changes
     */
    using ChangeCallback = std::function<void(const Config&)>;
    void on_change(ChangeCallback callback);
    
    // Delete copy/move constructors
    ConfigManager(const ConfigManager&) = delete;
    ConfigManager& operator=(const ConfigManager&) = delete;
    
private:
    ConfigManager() = default;
    
    Config config_;
    std::string config_path_;
    std::vector<ChangeCallback> callbacks_;
    mutable std::mutex mutex_;
    
    void notify_callbacks();
};

} // namespace cortexd

