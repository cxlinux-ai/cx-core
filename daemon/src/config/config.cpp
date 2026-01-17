/**
 * @file config.cpp
 * @brief Configuration implementation with YAML support (PR 1: Core Daemon)
 */

#include "cortexd/config.h"
#include "cortexd/logger.h"
#include <fstream>
#include <sstream>
#include <yaml-cpp/yaml.h>

namespace cortexd {

std::optional<Config> Config::load(const std::string& path) {
    try {
        std::string expanded_path = expand_path(path);
        
        // Check if file exists
        std::ifstream file(expanded_path);
        if (!file.good()) {
            LOG_WARN("Config", "Configuration file not found: " + expanded_path);
            return std::nullopt;
        }
        
        YAML::Node yaml = YAML::LoadFile(expanded_path);
        Config config;
        
        // Socket configuration
        if (yaml["socket"]) {
            auto socket = yaml["socket"];
            if (socket["path"]) config.socket_path = socket["path"].as<std::string>();
            if (socket["backlog"]) config.socket_backlog = socket["backlog"].as<int>();
            if (socket["timeout_ms"]) config.socket_timeout_ms = socket["timeout_ms"].as<int>();
        }
        
        // Rate limiting
        if (yaml["rate_limit"]) {
            auto rate = yaml["rate_limit"];
            if (rate["max_requests_per_sec"]) config.max_requests_per_sec = rate["max_requests_per_sec"].as<int>();
        }
        
        // Logging
        if (yaml["log_level"]) {
            config.log_level = yaml["log_level"].as<int>();
        }
        
        // Expand paths and validate
        config.expand_paths();
        std::string error = config.validate();
        if (!error.empty()) {
            LOG_ERROR("Config", "Configuration validation failed: " + error);
            return std::nullopt;
        }
        
        LOG_INFO("Config", "Configuration loaded from " + expanded_path);
        return config;
        
    } catch (const YAML::Exception& e) {
        LOG_ERROR("Config", "YAML parse error: " + std::string(e.what()));
        return std::nullopt;
    } catch (const std::exception& e) {
        LOG_ERROR("Config", "Error loading config: " + std::string(e.what()));
        return std::nullopt;
    }
}

bool Config::save(const std::string& path) const {
    try {
        std::string expanded_path = expand_path(path);
        
        YAML::Emitter out;
        out << YAML::BeginMap;
        
        // Socket
        out << YAML::Key << "socket" << YAML::Value << YAML::BeginMap;
        out << YAML::Key << "path" << YAML::Value << socket_path;
        out << YAML::Key << "backlog" << YAML::Value << socket_backlog;
        out << YAML::Key << "timeout_ms" << YAML::Value << socket_timeout_ms;
        out << YAML::EndMap;
        
        // Rate limiting
        out << YAML::Key << "rate_limit" << YAML::Value << YAML::BeginMap;
        out << YAML::Key << "max_requests_per_sec" << YAML::Value << max_requests_per_sec;
        out << YAML::EndMap;
        
        // Logging
        out << YAML::Key << "log_level" << YAML::Value << log_level;
        
        out << YAML::EndMap;
        
        std::ofstream file(expanded_path);
        if (!file.good()) {
            LOG_ERROR("Config", "Cannot write to " + expanded_path);
            return false;
        }
        
        file << out.c_str();
        LOG_INFO("Config", "Configuration saved to " + expanded_path);
        return true;
        
    } catch (const std::exception& e) {
        LOG_ERROR("Config", "Error saving config: " + std::string(e.what()));
        return false;
    }
}

void Config::expand_paths() {
    socket_path = expand_path(socket_path);
}

std::string Config::validate() const {
    if (socket_backlog <= 0) {
        return "socket_backlog must be positive";
    }
    if (socket_timeout_ms <= 0) {
        return "socket_timeout_ms must be positive";
    }
    if (max_requests_per_sec <= 0) {
        return "max_requests_per_sec must be positive";
    }
    if (log_level < 0 || log_level > 4) {
        return "log_level must be between 0 and 4";
    }
    return "";  // Valid
}

Config Config::defaults() {
    return Config{};
}

// ConfigManager implementation

ConfigManager& ConfigManager::instance() {
    static ConfigManager instance;
    return instance;
}

bool ConfigManager::load(const std::string& path) {
    Config config_copy;
    std::vector<ChangeCallback> callbacks_copy;
    
    {
        std::lock_guard<std::mutex> lock(mutex_);
        
        auto loaded = Config::load(path);
        if (!loaded) {
            LOG_WARN("ConfigManager", "Using default configuration");
            config_ = Config::defaults();
            config_.expand_paths();
            return false;
        }
        
        config_ = *loaded;
        config_path_ = path;
        
        // Copy for callback invocation outside the lock
        config_copy = config_;
        callbacks_copy = callbacks_;
    }
    
    // Invoke callbacks outside the lock to prevent deadlock
    notify_callbacks_unlocked(callbacks_copy, config_copy);
    return true;
}

bool ConfigManager::reload() {
    std::string path_copy;
    Config config_copy;
    std::vector<ChangeCallback> callbacks_copy;
    
    {
        std::lock_guard<std::mutex> lock(mutex_);
        
        // Copy config_path_ while holding mutex to avoid TOCTOU race
        if (config_path_.empty()) {
            LOG_WARN("ConfigManager", "No config path set, cannot reload");
            return false;
        }
        path_copy = config_path_;
    }
    
    // Load config outside the lock (Config::load is self-contained)
    auto loaded = Config::load(path_copy);
    if (!loaded) {
        LOG_ERROR("ConfigManager", "Failed to reload configuration");
        return false;
    }
    
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (config_path_ != path_copy) {
            LOG_WARN("ConfigManager", "Config path changed during reload; aborting");
            return false;
        }
        config_ = *loaded;
        
        // Copy for callback invocation outside the lock
        config_copy = config_;
        callbacks_copy = callbacks_;
    }
    
    // Invoke callbacks outside the lock to prevent deadlock
    notify_callbacks_unlocked(callbacks_copy, config_copy);
    LOG_INFO("ConfigManager", "Configuration reloaded");
    return true;
}

Config ConfigManager::get() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return config_;  // Return copy for thread safety
}

void ConfigManager::on_change(ChangeCallback callback) {
    std::lock_guard<std::mutex> lock(mutex_);
    callbacks_.push_back(std::move(callback));
}

void ConfigManager::notify_callbacks() {
    // This method should only be called while NOT holding the mutex
    // For internal use, prefer notify_callbacks_unlocked
    Config config_copy;
    std::vector<ChangeCallback> callbacks_copy;
    
    {
        std::lock_guard<std::mutex> lock(mutex_);
        config_copy = config_;
        callbacks_copy = callbacks_;
    }
    
    notify_callbacks_unlocked(callbacks_copy, config_copy);
}

void ConfigManager::notify_callbacks_unlocked(
    const std::vector<ChangeCallback>& callbacks,
    const Config& config) {
    // Invoke callbacks outside the lock to prevent deadlock if a callback
    // calls ConfigManager::get() or other mutex-guarded methods
    for (const auto& callback : callbacks) {
        try {
            callback(config);
        } catch (const std::exception& e) {
            LOG_ERROR("ConfigManager", "Callback error: " + std::string(e.what()));
        }
    }
}

} // namespace cortexd
