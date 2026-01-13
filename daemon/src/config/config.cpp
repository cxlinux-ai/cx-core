/**
 * @file config.cpp
 * @brief Configuration implementation with YAML support
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
        
        // LLM configuration
        if (yaml["llm"]) {
            auto llm = yaml["llm"];
            // Read backend type first
            if (llm["backend"]) config.llm_backend = llm["backend"].as<std::string>();
            
            // Local llama.cpp configuration
            if (llm["local"]) {
                auto local = llm["local"];
                if (local["base_url"]) config.llm_api_url = local["base_url"].as<std::string>();
            }
            
            // Cloud API configuration
            if (llm["cloud"]) {
                auto cloud = llm["cloud"];
                if (cloud["api_key_env"]) config.llm_api_key_env = cloud["api_key_env"].as<std::string>();
                // Only use cloud.provider to determine backend if backend is "cloud" (legacy support)
                // Don't override if backend is explicitly set to "local", "cloud_claude", etc.
                if (config.llm_backend == "cloud" && cloud["provider"]) {
                    std::string provider = cloud["provider"].as<std::string>();
                    if (provider == "claude") config.llm_backend = "cloud_claude";
                    else if (provider == "openai") config.llm_backend = "cloud_openai";
                }
            }
            
            // Legacy embedded LLM settings (deprecated)
            if (llm["model_path"]) config.model_path = llm["model_path"].as<std::string>();
            if (llm["context_length"]) config.llm_context_length = llm["context_length"].as<int>();
            if (llm["threads"]) config.llm_threads = llm["threads"].as<int>();
            if (llm["batch_size"]) config.llm_batch_size = llm["batch_size"].as<int>();
            if (llm["lazy_load"]) config.llm_lazy_load = llm["lazy_load"].as<bool>();
            if (llm["mmap"]) config.llm_mmap = llm["mmap"].as<bool>();
        }
        
        // Monitoring configuration
        if (yaml["monitoring"]) {
            auto mon = yaml["monitoring"];
            if (mon["interval_sec"]) config.monitor_interval_sec = mon["interval_sec"].as<int>();
            if (mon["enable_apt"]) config.enable_apt_monitor = mon["enable_apt"].as<bool>();
            if (mon["enable_cve"]) config.enable_cve_scanner = mon["enable_cve"].as<bool>();
            if (mon["enable_deps"]) config.enable_dependency_checker = mon["enable_deps"].as<bool>();
        }
        
        // Threshold configuration
        if (yaml["thresholds"]) {
            auto thresh = yaml["thresholds"];
            if (thresh["disk_warn"]) config.disk_warn_threshold = thresh["disk_warn"].as<double>();
            if (thresh["disk_crit"]) config.disk_crit_threshold = thresh["disk_crit"].as<double>();
            if (thresh["mem_warn"]) config.mem_warn_threshold = thresh["mem_warn"].as<double>();
            if (thresh["mem_crit"]) config.mem_crit_threshold = thresh["mem_crit"].as<double>();
        }
        
        // Alert configuration
        if (yaml["alerts"]) {
            auto alerts = yaml["alerts"];
            if (alerts["db_path"]) config.alert_db_path = alerts["db_path"].as<std::string>();
            if (alerts["retention_hours"]) config.alert_retention_hours = alerts["retention_hours"].as<int>();
            if (alerts["enable_ai"]) config.enable_ai_alerts = alerts["enable_ai"].as<bool>();
        }
        
        // Rate limiting
        if (yaml["rate_limit"]) {
            auto rate = yaml["rate_limit"];
            if (rate["max_requests_per_sec"]) config.max_requests_per_sec = rate["max_requests_per_sec"].as<int>();
            if (rate["max_inference_queue"]) config.max_inference_queue = rate["max_inference_queue"].as<int>();
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
        
        // LLM
        out << YAML::Key << "llm" << YAML::Value << YAML::BeginMap;
        out << YAML::Key << "model_path" << YAML::Value << model_path;
        out << YAML::Key << "context_length" << YAML::Value << llm_context_length;
        out << YAML::Key << "threads" << YAML::Value << llm_threads;
        out << YAML::Key << "batch_size" << YAML::Value << llm_batch_size;
        out << YAML::Key << "lazy_load" << YAML::Value << llm_lazy_load;
        out << YAML::Key << "mmap" << YAML::Value << llm_mmap;
        out << YAML::EndMap;
        
        // Monitoring
        out << YAML::Key << "monitoring" << YAML::Value << YAML::BeginMap;
        out << YAML::Key << "interval_sec" << YAML::Value << monitor_interval_sec;
        out << YAML::Key << "enable_apt" << YAML::Value << enable_apt_monitor;
        out << YAML::Key << "enable_cve" << YAML::Value << enable_cve_scanner;
        out << YAML::Key << "enable_deps" << YAML::Value << enable_dependency_checker;
        out << YAML::EndMap;
        
        // Thresholds
        out << YAML::Key << "thresholds" << YAML::Value << YAML::BeginMap;
        out << YAML::Key << "disk_warn" << YAML::Value << disk_warn_threshold;
        out << YAML::Key << "disk_crit" << YAML::Value << disk_crit_threshold;
        out << YAML::Key << "mem_warn" << YAML::Value << mem_warn_threshold;
        out << YAML::Key << "mem_crit" << YAML::Value << mem_crit_threshold;
        out << YAML::EndMap;
        
        // Alerts
        out << YAML::Key << "alerts" << YAML::Value << YAML::BeginMap;
        out << YAML::Key << "db_path" << YAML::Value << alert_db_path;
        out << YAML::Key << "retention_hours" << YAML::Value << alert_retention_hours;
        out << YAML::Key << "enable_ai" << YAML::Value << enable_ai_alerts;
        out << YAML::EndMap;
        
        // Rate limiting
        out << YAML::Key << "rate_limit" << YAML::Value << YAML::BeginMap;
        out << YAML::Key << "max_requests_per_sec" << YAML::Value << max_requests_per_sec;
        out << YAML::Key << "max_inference_queue" << YAML::Value << max_inference_queue;
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
    model_path = expand_path(model_path);
    alert_db_path = expand_path(alert_db_path);
}

std::string Config::validate() const {
    if (socket_backlog <= 0) {
        return "socket_backlog must be positive";
    }
    if (socket_timeout_ms <= 0) {
        return "socket_timeout_ms must be positive";
    }
    if (llm_context_length <= 0) {
        return "llm_context_length must be positive";
    }
    if (llm_threads <= 0) {
        return "llm_threads must be positive";
    }
    if (monitor_interval_sec <= 0) {
        return "monitor_interval_sec must be positive";
    }
    if (disk_warn_threshold <= 0 || disk_warn_threshold > 1) {
        return "disk_warn_threshold must be between 0 and 1";
    }
    if (disk_crit_threshold <= 0 || disk_crit_threshold > 1) {
        return "disk_crit_threshold must be between 0 and 1";
    }
    if (mem_warn_threshold <= 0 || mem_warn_threshold > 1) {
        return "mem_warn_threshold must be between 0 and 1";
    }
    if (mem_crit_threshold <= 0 || mem_crit_threshold > 1) {
        return "mem_crit_threshold must be between 0 and 1";
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
    notify_callbacks();
    return true;
}

bool ConfigManager::reload() {
    if (config_path_.empty()) {
        LOG_WARN("ConfigManager", "No config path set, cannot reload");
        return false;
    }
    
    std::lock_guard<std::mutex> lock(mutex_);
    
    auto loaded = Config::load(config_path_);
    if (!loaded) {
        LOG_ERROR("ConfigManager", "Failed to reload configuration");
        return false;
    }
    
    config_ = *loaded;
    notify_callbacks();
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
    for (const auto& callback : callbacks_) {
        try {
            callback(config_);
        } catch (const std::exception& e) {
            LOG_ERROR("ConfigManager", "Callback error: " + std::string(e.what()));
        }
    }
}

} // namespace cortexd

