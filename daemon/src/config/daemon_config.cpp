#include "daemon_config.h"
#include "logging.h"
#include <fstream>
#include <cstdlib>
#include <filesystem>

namespace cortex {
namespace daemon {

DaemonConfigManager& DaemonConfigManager::instance() {
    static DaemonConfigManager instance_;
    return instance_;
}

std::string DaemonConfigManager::expand_home_directory(const std::string& path) {
    if (path.empty() || path[0] != '~') {
        return path;
    }

    const char* home = std::getenv("HOME");
    if (!home) {
        return path;
    }

    return std::string(home) + path.substr(1);
}

bool DaemonConfigManager::load_config(const std::string& config_path) {
    try {
        std::string config_file;
        
        // If explicit path provided, use it
        if (!config_path.empty()) {
            config_file = config_path;
        } else {
            // Check config files in priority order:
            // 1. System config: /etc/cortex/daemon.conf
            // 2. User config: ~/.cortex/daemon.conf
            std::vector<std::string> config_paths = {
                "/etc/cortex/daemon.conf",
                expand_home_directory("~/.cortex/daemon.conf")
            };
            
            for (const auto& path : config_paths) {
                if (std::filesystem::exists(path)) {
                    config_file = path;
                    break;
                }
            }
            
            if (config_file.empty()) {
                Logger::info("ConfigManager", "No config file found, using defaults");
                return false;
            }
        }

        config_path_ = config_file;

        // FIX #4: Save previous model path for change detection
        previous_model_path_ = config_.model_path;

        if (!std::filesystem::exists(config_file)) {
            Logger::info("ConfigManager", "Config file not found: " + config_file);
            return false;
        }

        std::ifstream file(config_file);
        if (!file.is_open()) {
            Logger::error("ConfigManager", "Failed to open config file: " + config_file);
            return false;
        }

        // For now, we'll just parse YAML manually (could use yaml-cpp if needed)
        std::string line;
        while (std::getline(file, line)) {
            // Skip empty lines and comments
            if (line.empty() || line[0] == '#') continue;

            // Parse key: value format
            size_t pos = line.find(':');
            if (pos == std::string::npos) continue;

            std::string key = line.substr(0, pos);
            std::string value = line.substr(pos + 1);

            // Trim whitespace
            key.erase(0, key.find_first_not_of(" \t"));
            key.erase(key.find_last_not_of(" \t") + 1);
            value.erase(0, value.find_first_not_of(" \t"));
            value.erase(value.find_last_not_of(" \t") + 1);

            set_config_value(key, value);
        }

        // FIX #4: Log if model path changed
        if (config_.model_path != previous_model_path_) {
            Logger::warn("ConfigManager", 
                "Model path changed: " + previous_model_path_ + 
                " -> " + config_.model_path + " (restart daemon to apply)");
        }

        Logger::info("ConfigManager", "Configuration loaded from " + config_file);
        return true;

    } catch (const std::exception& e) {
        Logger::error("ConfigManager", "Failed to load config: " + std::string(e.what()));
        return false;
    }
}

bool DaemonConfigManager::save_config() {
    try {
        std::string config_file = expand_home_directory(config_.config_file);

        // Ensure directory exists
        std::filesystem::create_directories(std::filesystem::path(config_file).parent_path());

        std::ofstream file(config_file);
        if (!file.is_open()) {
            Logger::error("ConfigManager", "Failed to open config file for writing: " + config_file);
            return false;
        }

        file << "# Cortexd Configuration\n";
        file << "socket_path: " << config_.socket_path << "\n";
        file << "model_path: " << config_.model_path << "\n";
        file << "monitoring_interval_seconds: " << config_.monitoring_interval_seconds << "\n";
        file << "enable_cve_scanning: " << (config_.enable_cve_scanning ? "true" : "false") << "\n";
        file << "enable_journald_logging: " << (config_.enable_journald_logging ? "true" : "false") << "\n";
        file << "log_level: " << config_.log_level << "\n";

        Logger::info("ConfigManager", "Configuration saved to " + config_file);
        return true;

    } catch (const std::exception& e) {
        Logger::error("ConfigManager", "Failed to save config: " + std::string(e.what()));
        return false;
    }
}

void DaemonConfigManager::set_config_value(const std::string& key, const std::string& value) {
    if (key == "socket_path") {
        config_.socket_path = value;
    } else if (key == "model_path") {
        config_.model_path = value;
    } else if (key == "monitoring_interval_seconds") {
        config_.monitoring_interval_seconds = std::stoi(value);
    } else if (key == "enable_cve_scanning") {
        config_.enable_cve_scanning = (value == "true" || value == "1");
    } else if (key == "enable_journald_logging") {
        config_.enable_journald_logging = (value == "true" || value == "1");
    } else if (key == "log_level") {
        config_.log_level = std::stoi(value);
    } else if (key == "max_inference_queue_size") {
        config_.max_inference_queue_size = std::stoi(value);
    } else if (key == "memory_limit_mb") {
        config_.memory_limit_mb = std::stoi(value);
    }
}

json DaemonConfigManager::to_json() const {
    json j;
    j["socket_path"] = config_.socket_path;
    j["config_file"] = config_.config_file;
    j["model_path"] = config_.model_path;
    j["monitoring_interval_seconds"] = config_.monitoring_interval_seconds;
    j["enable_cve_scanning"] = config_.enable_cve_scanning;
    j["enable_journald_logging"] = config_.enable_journald_logging;
    j["log_level"] = config_.log_level;
    j["max_inference_queue_size"] = config_.max_inference_queue_size;
    j["memory_limit_mb"] = config_.memory_limit_mb;
    return j;
}

bool DaemonConfigManager::from_json(const json& j) {
    try {
        if (j.contains("socket_path")) config_.socket_path = j["socket_path"];
        if (j.contains("config_file")) config_.config_file = j["config_file"];
        if (j.contains("model_path")) config_.model_path = j["model_path"];
        if (j.contains("monitoring_interval_seconds")) 
            config_.monitoring_interval_seconds = j["monitoring_interval_seconds"];
        if (j.contains("enable_cve_scanning")) 
            config_.enable_cve_scanning = j["enable_cve_scanning"];
        if (j.contains("enable_journald_logging")) 
            config_.enable_journald_logging = j["enable_journald_logging"];
        if (j.contains("log_level")) config_.log_level = j["log_level"];
        if (j.contains("max_inference_queue_size")) 
            config_.max_inference_queue_size = j["max_inference_queue_size"];
        if (j.contains("memory_limit_mb")) 
            config_.memory_limit_mb = j["memory_limit_mb"];
        return true;
    } catch (const std::exception& e) {
        Logger::error("ConfigManager", "Failed to load from JSON: " + std::string(e.what()));
        return false;
    }
}

} // namespace daemon
} // namespace cortex
