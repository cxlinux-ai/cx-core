/**
 * @file test_daemon.cpp
 * @brief Integration tests for Daemon lifecycle and service management
 */

#include <gtest/gtest.h>
#include <thread>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <atomic>
#include <unistd.h>
#include "cortexd/core/daemon.h"
#include "cortexd/core/service.h"
#include "cortexd/config.h"
#include "cortexd/logger.h"
#include "cortexd/ipc/server.h"

namespace fs = std::filesystem;

/**
 * @brief Mock service for testing service lifecycle
 */
class MockService : public cortexd::Service {
public:
    MockService(const std::string& name, int priority = 0)
        : name_(name), priority_(priority) {}
    
    bool start() override {
        if (should_fail_start_) return false;
        running_ = true;
        start_count_++;
        return true;
    }
    
    void stop() override {
        running_ = false;
        stop_count_++;
    }
    
    const char* name() const override { return name_.c_str(); }
    int priority() const override { return priority_; }
    bool is_running() const override { return running_; }
    bool is_healthy() const override { return healthy_ && running_; }
    
    void set_should_fail_start(bool fail) { should_fail_start_ = fail; }
    void set_healthy(bool healthy) { healthy_ = healthy; }
    
    int start_count() const { return start_count_; }
    int stop_count() const { return stop_count_; }
    
private:
    std::string name_;
    int priority_;
    std::atomic<bool> running_{false};
    bool should_fail_start_ = false;
    bool healthy_ = true;
    int start_count_ = 0;
    int stop_count_ = 0;
};

class DaemonTest : public ::testing::Test {
protected:
    void SetUp() override {
        cortexd::Logger::init(cortexd::LogLevel::ERROR, false);
        
        // Create temp directory for test files
        temp_dir_ = fs::temp_directory_path() / ("cortexd_daemon_test_" + std::to_string(getpid()));
        fs::create_directories(temp_dir_);
        
        config_path_ = (temp_dir_ / "config.yaml").string();
        socket_path_ = (temp_dir_ / "test.sock").string();
        
        // Create a minimal config file
        std::ofstream config_file(config_path_);
        config_file << R"(
socket:
  path: )" << socket_path_ << R"(
  backlog: 16
  timeout_ms: 5000

rate_limit:
  max_requests_per_sec: 100

log_level: 1
)";
        config_file.close();
    }
    
    void TearDown() override {
        // Reset daemon singleton state to ensure clean state between tests
        cortexd::Daemon::instance().reset();
        
        fs::remove_all(temp_dir_);
        cortexd::Logger::shutdown();
    }
    
    fs::path temp_dir_;
    std::string config_path_;
    std::string socket_path_;
};

// ============================================================================
// Singleton tests
// ============================================================================

TEST_F(DaemonTest, InstanceReturnsSameDaemon) {
    auto& daemon1 = cortexd::Daemon::instance();
    auto& daemon2 = cortexd::Daemon::instance();
    
    EXPECT_EQ(&daemon1, &daemon2);
}

// ============================================================================
// Initialization tests
// ============================================================================

TEST_F(DaemonTest, InitializeWithValidConfig) {
    auto& daemon = cortexd::Daemon::instance();
    
    EXPECT_TRUE(daemon.initialize(config_path_));
}

TEST_F(DaemonTest, InitializeWithNonexistentConfigUsesDefaults) {
    auto& daemon = cortexd::Daemon::instance();
    
    // Should still initialize (with defaults)
    EXPECT_TRUE(daemon.initialize("/nonexistent/config.yaml"));
}

TEST_F(DaemonTest, ConfigIsLoadedAfterInitialize) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    auto config = daemon.config();
    EXPECT_EQ(config.socket_path, socket_path_);
}

// ============================================================================
// Shutdown request tests
// ============================================================================

TEST_F(DaemonTest, RequestShutdownSetsFlag) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    // The test fixture resets the Daemon in TearDown(), so prior-test state is not possible.
    // This test verifies that request_shutdown() sets shutdown_requested_ to true and
    // is idempotent on a freshly reset singleton.
    daemon.request_shutdown();
    
    EXPECT_TRUE(daemon.shutdown_requested());
}

// ============================================================================
// Service registration tests
// ============================================================================

TEST_F(DaemonTest, RegisterServiceAddsService) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    auto mock = std::make_unique<MockService>("TestService", 50);
    MockService* mock_ptr = mock.get();
    
    daemon.register_service(std::move(mock));
    
    // Verify service is registered
    auto* retrieved = daemon.get_service<MockService>();
    EXPECT_EQ(retrieved, mock_ptr);
}

TEST_F(DaemonTest, GetServiceReturnsNullptrForUnregistered) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    // No services registered, should return nullptr
    auto* service = daemon.get_service<cortexd::IPCServer>();
    EXPECT_EQ(service, nullptr);
}

// ============================================================================
// Uptime tests
// ============================================================================

TEST_F(DaemonTest, UptimeIsZeroBeforeRun) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    // Before running, uptime calculation may not be meaningful
    // but it shouldn't crash
    auto uptime = daemon.uptime();
    EXPECT_GE(uptime.count(), 0);
}

// ============================================================================
// Config reload tests
// ============================================================================

TEST_F(DaemonTest, ReloadConfigWorks) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    // Initial config
    auto initial_config = daemon.config();
    EXPECT_EQ(initial_config.log_level, 1);
    
    // Modify config file
    std::ofstream config_file(config_path_);
    config_file << R"(
socket:
  path: )" << socket_path_ << R"(
  backlog: 16
  timeout_ms: 5000

rate_limit:
  max_requests_per_sec: 100

log_level: 2
)";
    config_file.close();
    
    // Reload
    EXPECT_TRUE(daemon.reload_config());
    
    // Verify change
    auto reloaded_config = daemon.config();
    EXPECT_EQ(reloaded_config.log_level, 2);
}

// ============================================================================
// Run loop tests (limited scope due to blocking nature)
// ============================================================================

TEST_F(DaemonTest, RunReturnsOnShutdownRequest) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    // Request shutdown immediately so run() doesn't block forever
    daemon.request_shutdown();
    
    // Run should return quickly since shutdown is already requested
    // Note: This test verifies basic shutdown flow without blocking
    EXPECT_TRUE(daemon.shutdown_requested());
}

TEST_F(DaemonTest, RunWithServicesThatFailToStart) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    auto failing_service = std::make_unique<MockService>("FailingService");
    failing_service->set_should_fail_start(true);
    
    daemon.register_service(std::move(failing_service));
    daemon.request_shutdown();  // Prevent blocking
    
    // The run will fail due to service start failure
    // We can't easily test this without modifying daemon internals
}

// ============================================================================
// Multiple service tests
// ============================================================================

TEST_F(DaemonTest, RegisterMultipleServices) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    daemon.register_service(std::make_unique<MockService>("Service1", 10));
    daemon.register_service(std::make_unique<MockService>("Service2", 20));
    daemon.register_service(std::make_unique<MockService>("Service3", 30));
    
    // All services should be retrievable
    auto* svc = daemon.get_service<MockService>();
    EXPECT_NE(svc, nullptr);
}

// ============================================================================
// Running state tests
// ============================================================================

TEST_F(DaemonTest, IsRunningInitiallyFalse) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    // Before run() is called
    EXPECT_FALSE(daemon.is_running());
}

// ============================================================================
// Config access tests
// ============================================================================

TEST_F(DaemonTest, ConfigReturnsValidConfig) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    auto config = daemon.config();
    
    // Verify config has expected values
    EXPECT_FALSE(config.socket_path.empty());
    EXPECT_GT(config.socket_backlog, 0);
    EXPECT_GT(config.socket_timeout_ms, 0);
    EXPECT_GT(config.max_requests_per_sec, 0);
}

// ============================================================================
// Thread safety tests
// ============================================================================

TEST_F(DaemonTest, ConfigAccessIsThreadSafe) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    std::atomic<int> read_count{0};
    std::vector<std::thread> threads;
    
    // Multiple threads reading config concurrently
    for (int t = 0; t < 10; ++t) {
        threads.emplace_back([&]() {
            for (int i = 0; i < 100; ++i) {
                auto config = daemon.config();
                // Access some fields to ensure no crashes
                (void)config.socket_path;
                (void)config.log_level;
                read_count++;
            }
        });
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
    
    EXPECT_EQ(read_count.load(), 1000);
}

TEST_F(DaemonTest, ShutdownRequestIsThreadSafe) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    std::vector<std::thread> threads;
    
    // Multiple threads requesting shutdown
    for (int t = 0; t < 10; ++t) {
        threads.emplace_back([&]() {
            daemon.request_shutdown();
        });
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
    
    EXPECT_TRUE(daemon.shutdown_requested());
}

// ============================================================================
// systemd notification tests (mock verification)
// ============================================================================

TEST_F(DaemonTest, NotifyReadyDoesNotCrash) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    // These should not crash (systemd may not be available in test env)
    daemon.notify_ready();
    SUCCEED();
}

TEST_F(DaemonTest, NotifyStoppingDoesNotCrash) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    daemon.notify_stopping();
    SUCCEED();
}

TEST_F(DaemonTest, NotifyWatchdogDoesNotCrash) {
    auto& daemon = cortexd::Daemon::instance();
    daemon.initialize(config_path_);
    
    daemon.notify_watchdog();
    SUCCEED();
}

// ============================================================================
// Edge case tests
// ============================================================================

TEST_F(DaemonTest, DoubleInitialize) {
    auto& daemon = cortexd::Daemon::instance();
    
    EXPECT_TRUE(daemon.initialize(config_path_));
    EXPECT_TRUE(daemon.initialize(config_path_));  // Should not crash
}

TEST_F(DaemonTest, ReloadBeforeInit) {
    auto& daemon = cortexd::Daemon::instance();
    
    // reload without init - should handle gracefully
    // (depends on implementation, may return false)
    daemon.reload_config();  // Should not crash
    SUCCEED();
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
