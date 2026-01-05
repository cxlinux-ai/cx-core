#pragma once

#include <string>
#include <map>
#include <memory>
#include <nlohmann/json.hpp>

namespace cortex {
namespace daemon {

using json = nlohmann::json;

// Configuration structure
struct DaemonConfig {
    std::string socket_path = "/run/cortex.sock";
    std::string config_file = "~/.cortex/daemon.conf";
    std::string model_path = "~/.cortex/models/default.gguf";
    int monitoring_interval_seconds = 300;
    bool enable_cve_scanning = true;
    bool enable_journald_logging = true;
    int log_level = 1; // 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR
    int max_inference_queue_size = 100;
    int memory_limit_mb = 150;
};

// Configuration manager
class DaemonConfigManager {
public:
    static DaemonConfigManager& instance();

    // Load config from file
    bool load_config(const std::string& config_path = "");

    // Save config to file
    bool save_config();

    // Get config
    const DaemonConfig& get_config() const { return config_; }

    // Update config value
    void set_config_value(const std::string& key, const std::string& value);

    // Export to JSON
    json to_json() const;

    // Import from JSON
    bool from_json(const json& j);

    // FIX #4: Check if model path changed (for hot reload support)
    std::string get_previous_model_path() const { return previous_model_path_; }

private:
    DaemonConfigManager() = default;
    ~DaemonConfigManager() = default;

    DaemonConfig config_;
    std::string config_path_;
    std::string previous_model_path_;  // FIX #4: Track previous path for change detection

    // Expand ~ in paths
    std::string expand_home_directory(const std::string& path);
};

} // namespace daemon
} // namespace cortex
