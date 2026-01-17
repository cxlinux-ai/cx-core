/**
 * @file test_config.cpp
 * @brief Unit tests for Config and ConfigManager
 */

#include <gtest/gtest.h>
#include <fstream>
#include <filesystem>
#include <chrono>
#include <unistd.h>
#include "cortexd/config.h"
#include "cortexd/logger.h"

namespace fs = std::filesystem;

class ConfigTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Initialize logger in non-journald mode for tests
        cortexd::Logger::init(cortexd::LogLevel::ERROR, false);
        
        // Create a temp directory for test files with unique suffix to avoid collisions
        temp_dir_ = fs::temp_directory_path() / ("cortexd_test_" + std::to_string(getpid()) + "_" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
        fs::create_directories(temp_dir_);
    }
    
    void TearDown() override {
        // Clean up temp directory
        fs::remove_all(temp_dir_);
        cortexd::Logger::shutdown();
    }
    
    fs::path temp_dir_;
    
    // Helper to write a config file
    void write_config(const std::string& filename, const std::string& content) {
        std::ofstream file(temp_dir_ / filename);
        file << content;
        file.close();
    }
};

// ============================================================================
// Config::defaults() tests
// ============================================================================

TEST_F(ConfigTest, DefaultsReturnsValidConfig) {
    auto config = cortexd::Config::defaults();
    
    EXPECT_EQ(config.socket_path, "/run/cortex/cortex.sock");
    EXPECT_EQ(config.socket_backlog, 16);
    EXPECT_EQ(config.socket_timeout_ms, 5000);
    EXPECT_EQ(config.max_requests_per_sec, 100);
    EXPECT_EQ(config.log_level, 1);
}

TEST_F(ConfigTest, DefaultsPassesValidation) {
    auto config = cortexd::Config::defaults();
    std::string error = config.validate();
    
    EXPECT_TRUE(error.empty()) << "Validation error: " << error;
}

// ============================================================================
// Config::validate() tests
// ============================================================================

TEST_F(ConfigTest, ValidateRejectsZeroSocketBacklog) {
    auto config = cortexd::Config::defaults();
    config.socket_backlog = 0;
    
    std::string error = config.validate();
    EXPECT_FALSE(error.empty());
    EXPECT_TRUE(error.find("socket_backlog") != std::string::npos);
}

TEST_F(ConfigTest, ValidateRejectsNegativeSocketBacklog) {
    auto config = cortexd::Config::defaults();
    config.socket_backlog = -5;
    
    std::string error = config.validate();
    EXPECT_FALSE(error.empty());
}

TEST_F(ConfigTest, ValidateRejectsZeroSocketTimeout) {
    auto config = cortexd::Config::defaults();
    config.socket_timeout_ms = 0;
    
    std::string error = config.validate();
    EXPECT_FALSE(error.empty());
    EXPECT_TRUE(error.find("socket_timeout_ms") != std::string::npos);
}

TEST_F(ConfigTest, ValidateRejectsZeroMaxRequests) {
    auto config = cortexd::Config::defaults();
    config.max_requests_per_sec = 0;
    
    std::string error = config.validate();
    EXPECT_FALSE(error.empty());
    EXPECT_TRUE(error.find("max_requests_per_sec") != std::string::npos);
}

TEST_F(ConfigTest, ValidateRejectsInvalidLogLevel) {
    auto config = cortexd::Config::defaults();
    config.log_level = 5;  // Valid range is 0-4 (DEBUG=0, INFO=1, WARN=2, ERROR=3, CRITICAL=4)
    
    std::string error = config.validate();
    EXPECT_FALSE(error.empty());
    EXPECT_TRUE(error.find("log_level") != std::string::npos);
}

TEST_F(ConfigTest, ValidateRejectsNegativeLogLevel) {
    auto config = cortexd::Config::defaults();
    config.log_level = -1;
    
    std::string error = config.validate();
    EXPECT_FALSE(error.empty());
}

TEST_F(ConfigTest, ValidateAcceptsAllValidLogLevels) {
    auto config = cortexd::Config::defaults();
    
    // Valid range is 0-4 (DEBUG=0, INFO=1, WARN=2, ERROR=3, CRITICAL=4)
    for (int level = 0; level <= 4; ++level) {
        config.log_level = level;
        std::string error = config.validate();
        EXPECT_TRUE(error.empty()) << "Log level " << level << " should be valid";
    }
}

// ============================================================================
// Config::load() tests
// ============================================================================

TEST_F(ConfigTest, LoadReturnsNulloptForNonexistentFile) {
    auto result = cortexd::Config::load("/nonexistent/path/config.yaml");
    EXPECT_FALSE(result.has_value());
}

TEST_F(ConfigTest, LoadParsesValidYaml) {
    write_config("valid.yaml", R"(
socket:
  path: /tmp/test.sock
  backlog: 32
  timeout_ms: 10000

rate_limit:
  max_requests_per_sec: 200

log_level: 2
)");
    
    auto result = cortexd::Config::load((temp_dir_ / "valid.yaml").string());
    
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->socket_path, "/tmp/test.sock");
    EXPECT_EQ(result->socket_backlog, 32);
    EXPECT_EQ(result->socket_timeout_ms, 10000);
    EXPECT_EQ(result->max_requests_per_sec, 200);
    EXPECT_EQ(result->log_level, 2);
}

TEST_F(ConfigTest, LoadUsesDefaultsForMissingFields) {
    write_config("partial.yaml", R"(
socket:
  path: /tmp/partial.sock
)");
    
    auto result = cortexd::Config::load((temp_dir_ / "partial.yaml").string());
    
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->socket_path, "/tmp/partial.sock");
    // Other fields should have defaults
    EXPECT_EQ(result->socket_backlog, 16);
    EXPECT_EQ(result->socket_timeout_ms, 5000);
    EXPECT_EQ(result->max_requests_per_sec, 100);
    EXPECT_EQ(result->log_level, 1);
}

TEST_F(ConfigTest, LoadReturnsNulloptForInvalidYaml) {
    write_config("invalid.yaml", R"(
socket:
  path: [this is not valid yaml
  backlog: "not a number"
)");
    
    auto result = cortexd::Config::load((temp_dir_ / "invalid.yaml").string());
    EXPECT_FALSE(result.has_value());
}

TEST_F(ConfigTest, LoadReturnsNulloptForInvalidConfig) {
    write_config("invalid_values.yaml", R"(
socket:
  path: /tmp/test.sock
  backlog: -1

log_level: 1
)");
    
    auto result = cortexd::Config::load((temp_dir_ / "invalid_values.yaml").string());
    EXPECT_FALSE(result.has_value());
}

// ============================================================================
// Config::save() tests
// ============================================================================

TEST_F(ConfigTest, SaveCreatesValidYamlFile) {
    auto config = cortexd::Config::defaults();
    config.socket_path = "/tmp/saved.sock";
    config.max_requests_per_sec = 50;
    
    std::string save_path = (temp_dir_ / "saved.yaml").string();
    ASSERT_TRUE(config.save(save_path));
    
    // Verify file exists
    EXPECT_TRUE(fs::exists(save_path));
    
    // Reload and verify
    auto reloaded = cortexd::Config::load(save_path);
    ASSERT_TRUE(reloaded.has_value());
    EXPECT_EQ(reloaded->socket_path, "/tmp/saved.sock");
    EXPECT_EQ(reloaded->max_requests_per_sec, 50);
}

// ============================================================================
// Config::expand_paths() tests
// ============================================================================

TEST_F(ConfigTest, ExpandPathsExpandsTilde) {
    auto config = cortexd::Config::defaults();
    config.socket_path = "~/test.sock";
    
    config.expand_paths();
    
    // Should start with home directory, not ~
    EXPECT_NE(config.socket_path[0], '~');
    EXPECT_TRUE(config.socket_path.find("/test.sock") != std::string::npos);
}

TEST_F(ConfigTest, ExpandPathsLeavesAbsolutePathsUnchanged) {
    auto config = cortexd::Config::defaults();
    config.socket_path = "/absolute/path.sock";
    
    config.expand_paths();
    
    EXPECT_EQ(config.socket_path, "/absolute/path.sock");
}

// ============================================================================
// expand_path() function tests
// ============================================================================

TEST_F(ConfigTest, ExpandPathFunctionExpandsTilde) {
    std::string path = "~/.cortex/test";
    std::string expanded = cortexd::expand_path(path);
    
    EXPECT_NE(expanded[0], '~');
    EXPECT_TRUE(expanded.find("/.cortex/test") != std::string::npos);
}

TEST_F(ConfigTest, ExpandPathFunctionHandlesEmptyString) {
    std::string path = "";
    std::string expanded = cortexd::expand_path(path);
    
    EXPECT_TRUE(expanded.empty());
}

TEST_F(ConfigTest, ExpandPathFunctionHandlesAbsolutePath) {
    std::string path = "/absolute/path";
    std::string expanded = cortexd::expand_path(path);
    
    EXPECT_EQ(expanded, "/absolute/path");
}

// ============================================================================
// ConfigManager tests
// ============================================================================

TEST_F(ConfigTest, ConfigManagerReturnsSameInstance) {
    auto& instance1 = cortexd::ConfigManager::instance();
    auto& instance2 = cortexd::ConfigManager::instance();
    
    EXPECT_EQ(&instance1, &instance2);
}

TEST_F(ConfigTest, ConfigManagerLoadReturnsDefaultsOnFailure) {
    auto& manager = cortexd::ConfigManager::instance();
    
    // Load non-existent file
    bool result = manager.load("/nonexistent/config.yaml");
    EXPECT_FALSE(result);
    
    // Should still have valid defaults
    auto config = manager.get();
    EXPECT_EQ(config.socket_path, "/run/cortex/cortex.sock");
}

TEST_F(ConfigTest, ConfigManagerLoadSucceedsWithValidFile) {
    write_config("manager_test.yaml", R"(
socket:
  path: /tmp/manager.sock

log_level: 0
)");
    
    auto& manager = cortexd::ConfigManager::instance();
    bool result = manager.load((temp_dir_ / "manager_test.yaml").string());
    
    EXPECT_TRUE(result);
    
    auto config = manager.get();
    EXPECT_EQ(config.socket_path, "/tmp/manager.sock");
    EXPECT_EQ(config.log_level, 0);
}

TEST_F(ConfigTest, ConfigManagerReloadWorks) {
    write_config("reload_test.yaml", R"(
socket:
  path: /tmp/original.sock
log_level: 1
)");
    
    auto& manager = cortexd::ConfigManager::instance();
    manager.load((temp_dir_ / "reload_test.yaml").string());
    
    // Modify the file
    write_config("reload_test.yaml", R"(
socket:
  path: /tmp/modified.sock
log_level: 2
)");
    
    // Reload
    bool result = manager.reload();
    EXPECT_TRUE(result);
    
    auto config = manager.get();
    EXPECT_EQ(config.socket_path, "/tmp/modified.sock");
    EXPECT_EQ(config.log_level, 2);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
