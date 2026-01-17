/**
 * @file config.h
 * @brief Configuration management for cortexd (PR 1: Core Daemon)
 */

#pragma once

#include <string>
#include <optional>
#include <mutex>
#include <vector>
#include <functional>
#include <cstdlib>

namespace cortexd {

// Default configuration path
constexpr const char* DEFAULT_CONFIG_PATH = "/etc/cortex/daemon.yaml";

/**
 * @brief Expand ~ to home directory in paths
 */
inline std::string expand_path(const std::string& path) {
    if (path.empty() || path[0] != '~') {
        return path;
    }
    const char* home = std::getenv("HOME");
    if (!home) {
        return path;
    }
    return std::string(home) + path.substr(1);
}

/**
 * @brief Daemon configuration structure (PR 1: Core fields only)
 */
struct Config {
    // Socket configuration
    std::string socket_path = "/run/cortex/cortex.sock";
    int socket_backlog = 16;
    int socket_timeout_ms = 5000;
    
    // Rate limiting
    int max_requests_per_sec = 100;
    
    // Logging
    int log_level = 1;  // 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR, 4=CRITICAL
    
    /**
     * @brief Load configuration from YAML file
     * @param path Path to configuration file
     * @return Config if successful, nullopt on error
     */
    static std::optional<Config> load(const std::string& path);
    
    /**
     * @brief Save configuration to YAML file
     * @param path Path to save to
     * @return true if successful
     */
    bool save(const std::string& path) const;
    
    /**
     * @brief Get default configuration
     */
    static Config defaults();
    
    /**
     * @brief Expand ~ in all path fields
     */
    void expand_paths();
    
    /**
     * @brief Validate configuration
     * @return Empty string if valid, error message otherwise
     */
    std::string validate() const;
};

/**
 * @brief Configuration manager singleton
 * 
 * Thread-safe configuration management with change notification support.
 */
class ConfigManager {
public:
    using ChangeCallback = std::function<void(const Config&)>;
    
    /**
     * @brief Get singleton instance
     */
    static ConfigManager& instance();
    
    /**
     * @brief Load configuration from file
     * @param path Path to configuration file
     * @return true if loaded successfully
     */
    bool load(const std::string& path);
    
    /**
     * @brief Reload configuration from previously loaded path
     * @return true if reloaded successfully
     */
    bool reload();
    
    /**
     * @brief Get current configuration (returns copy for thread safety)
     */
    Config get() const;
    
    /**
     * @brief Register callback for configuration changes
     * @param callback Function to call when config changes
     */
    void on_change(ChangeCallback callback);
    
    // Delete copy/move
    ConfigManager(const ConfigManager&) = delete;
    ConfigManager& operator=(const ConfigManager&) = delete;
    
private:
    ConfigManager() = default;
    
    Config config_;
    std::string config_path_;
    mutable std::mutex mutex_;
    std::vector<ChangeCallback> callbacks_;
    
    /**
     * @brief Notify all registered callbacks (acquires mutex internally)
     */
    void notify_callbacks();
    
    /**
     * @brief Notify callbacks without acquiring mutex
     * @param callbacks Copy of callbacks to invoke
     * @param config Copy of config to pass to callbacks
     * 
     * This method is used to invoke callbacks outside the lock to prevent
     * deadlock if a callback calls ConfigManager::get() or other methods.
     */
    void notify_callbacks_unlocked(
        const std::vector<ChangeCallback>& callbacks,
        const Config& config);
};

} // namespace cortexd
