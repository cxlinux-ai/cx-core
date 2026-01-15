/**
 * @file test_handlers.cpp
 * @brief Integration tests for IPC handlers
 */

#include <gtest/gtest.h>
#include <thread>
#include <chrono>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <filesystem>
#include <fstream>
#include "cortexd/ipc/server.h"
#include "cortexd/ipc/handlers.h"
#include "cortexd/ipc/protocol.h"
#include "cortexd/config.h"
#include "cortexd/core/daemon.h"
#include "cortexd/logger.h"

namespace fs = std::filesystem;

class HandlersTest : public ::testing::Test {
protected:
    void SetUp() override {
        cortexd::Logger::init(cortexd::LogLevel::ERROR, false);
        
        // Create temp directory for test files
        temp_dir_ = fs::temp_directory_path() / ("cortexd_handlers_test_" + std::to_string(getpid()));
        fs::create_directories(temp_dir_);
        
        socket_path_ = (temp_dir_ / "test.sock").string();
        config_path_ = (temp_dir_ / "config.yaml").string();
        
        // Create a test config file
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
        
        // Load config
        cortexd::ConfigManager::instance().load(config_path_);
    }
    
    void TearDown() override {
        if (server_) {
            server_->stop();
            server_.reset();
        }
        
        fs::remove_all(temp_dir_);
        cortexd::Logger::shutdown();
    }
    
    void start_server_with_handlers() {
        auto config = cortexd::ConfigManager::instance().get();
        server_ = std::make_unique<cortexd::IPCServer>(socket_path_, config.max_requests_per_sec);
        cortexd::Handlers::register_all(*server_);
        ASSERT_TRUE(server_->start());
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    
    std::string send_request(const std::string& request) {
        int sock = socket(AF_UNIX, SOCK_STREAM, 0);
        if (sock == -1) return "";
        
        struct sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, socket_path_.c_str(), sizeof(addr.sun_path) - 1);
        
        if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) == -1) {
            close(sock);
            return "";
        }
        
        // Check send() return value to ensure data was sent successfully
        ssize_t sent = send(sock, request.c_str(), request.length(), 0);
        if (sent <= 0 || static_cast<size_t>(sent) < request.length()) {
            close(sock);
            return "";  // Send failed or partial send
        }
        
        char buffer[65536];
        ssize_t bytes = recv(sock, buffer, sizeof(buffer) - 1, 0);
        close(sock);
        
        if (bytes <= 0) return "";
        
        buffer[bytes] = '\0';
        return std::string(buffer);
    }
    
    cortexd::json send_json_request(const std::string& method, 
                                     const cortexd::json& params = cortexd::json::object()) {
        cortexd::json request = {
            {"method", method},
            {"params", params}
        };
        
        std::string response = send_request(request.dump());
        if (response.empty()) {
            return cortexd::json{{"error", "empty response"}};
        }
        
        return cortexd::json::parse(response);
    }
    
    fs::path temp_dir_;
    std::string socket_path_;
    std::string config_path_;
    std::unique_ptr<cortexd::IPCServer> server_;
};

// ============================================================================
// Ping handler tests
// ============================================================================

TEST_F(HandlersTest, PingReturnsSuccess) {
    start_server_with_handlers();
    
    auto response = send_json_request("ping");
    
    EXPECT_TRUE(response["success"]);
    EXPECT_TRUE(response["result"]["pong"]);
}

TEST_F(HandlersTest, PingIgnoresParams) {
    start_server_with_handlers();
    
    auto response = send_json_request("ping", {{"ignored", "param"}});
    
    EXPECT_TRUE(response["success"]);
    EXPECT_TRUE(response["result"]["pong"]);
}

// ============================================================================
// Version handler tests
// ============================================================================

TEST_F(HandlersTest, VersionReturnsVersionAndName) {
    start_server_with_handlers();
    
    auto response = send_json_request("version");
    
    EXPECT_TRUE(response["success"]);
    EXPECT_TRUE(response["result"].contains("version"));
    EXPECT_TRUE(response["result"].contains("name"));
    EXPECT_EQ(response["result"]["name"], "cortexd");
}

TEST_F(HandlersTest, VersionReturnsNonEmptyVersion) {
    start_server_with_handlers();
    
    auto response = send_json_request("version");
    
    std::string version = response["result"]["version"];
    EXPECT_FALSE(version.empty());
}

// ============================================================================
// Config.get handler tests
// ============================================================================

TEST_F(HandlersTest, ConfigGetReturnsConfig) {
    start_server_with_handlers();
    
    auto response = send_json_request("config.get");
    
    EXPECT_TRUE(response["success"]);
    EXPECT_TRUE(response["result"].contains("socket_path"));
    EXPECT_TRUE(response["result"].contains("socket_backlog"));
    EXPECT_TRUE(response["result"].contains("socket_timeout_ms"));
    EXPECT_TRUE(response["result"].contains("max_requests_per_sec"));
    EXPECT_TRUE(response["result"].contains("log_level"));
}

TEST_F(HandlersTest, ConfigGetReturnsCorrectValues) {
    start_server_with_handlers();
    
    auto response = send_json_request("config.get");
    
    EXPECT_TRUE(response["success"]);
    EXPECT_EQ(response["result"]["socket_path"], socket_path_);
    EXPECT_EQ(response["result"]["socket_backlog"], 16);
    EXPECT_EQ(response["result"]["socket_timeout_ms"], 5000);
    EXPECT_EQ(response["result"]["max_requests_per_sec"], 100);
    EXPECT_EQ(response["result"]["log_level"], 1);
}

// ============================================================================
// Config.reload handler tests
// ============================================================================

TEST_F(HandlersTest, ConfigReloadSucceeds) {
    start_server_with_handlers();
    
    auto response = send_json_request("config.reload");
    
    EXPECT_TRUE(response["success"]);
    EXPECT_TRUE(response["result"]["reloaded"]);
}

TEST_F(HandlersTest, ConfigReloadPicksUpChanges) {
    start_server_with_handlers();
    
    // Verify initial value
    auto initial = send_json_request("config.get");
    EXPECT_EQ(initial["result"]["log_level"], 1);
    
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
    
    // Reload config
    auto reload_response = send_json_request("config.reload");
    EXPECT_TRUE(reload_response["success"]);
    
    // Verify new value
    auto updated = send_json_request("config.get");
    EXPECT_EQ(updated["result"]["log_level"], 2);
}

// ============================================================================
// Shutdown handler tests
// ============================================================================

TEST_F(HandlersTest, ShutdownReturnsInitiated) {
    start_server_with_handlers();
    
    auto response = send_json_request("shutdown");
    
    EXPECT_TRUE(response["success"]);
    EXPECT_EQ(response["result"]["shutdown"], "initiated");
}

// Note: We can't easily test that shutdown actually stops the daemon
// in this test environment since we're not running the full daemon

// ============================================================================
// Unknown method tests
// ============================================================================

TEST_F(HandlersTest, UnknownMethodReturnsError) {
    start_server_with_handlers();
    
    auto response = send_json_request("unknown.method");
    
    EXPECT_FALSE(response["success"]);
    EXPECT_EQ(response["error"]["code"], cortexd::ErrorCodes::METHOD_NOT_FOUND);
}

TEST_F(HandlersTest, StatusMethodNotAvailableInPR1) {
    start_server_with_handlers();
    
    // Status handler is not registered in PR 1
    auto response = send_json_request("status");
    
    EXPECT_FALSE(response["success"]);
    EXPECT_EQ(response["error"]["code"], cortexd::ErrorCodes::METHOD_NOT_FOUND);
}

TEST_F(HandlersTest, HealthMethodNotAvailableInPR1) {
    start_server_with_handlers();
    
    // Health handler is not registered in PR 1
    auto response = send_json_request("health");
    
    EXPECT_FALSE(response["success"]);
    EXPECT_EQ(response["error"]["code"], cortexd::ErrorCodes::METHOD_NOT_FOUND);
}

TEST_F(HandlersTest, AlertsMethodNotAvailableInPR1) {
    start_server_with_handlers();
    
    // Alerts handler is not registered in PR 1
    auto response = send_json_request("alerts");
    
    EXPECT_FALSE(response["success"]);
    EXPECT_EQ(response["error"]["code"], cortexd::ErrorCodes::METHOD_NOT_FOUND);
}

// ============================================================================
// Response format tests
// ============================================================================

TEST_F(HandlersTest, AllResponsesHaveTimestamp) {
    start_server_with_handlers();
    
    std::vector<std::string> methods = {"ping", "version", "config.get"};
    
    for (const auto& method : methods) {
        auto response = send_json_request(method);
        EXPECT_TRUE(response.contains("timestamp")) 
            << "Method " << method << " should include timestamp";
    }
}

TEST_F(HandlersTest, SuccessResponsesHaveResult) {
    start_server_with_handlers();
    
    std::vector<std::string> methods = {"ping", "version", "config.get"};
    
    for (const auto& method : methods) {
        auto response = send_json_request(method);
        EXPECT_TRUE(response["success"]) << "Method " << method << " should succeed";
        EXPECT_TRUE(response.contains("result")) 
            << "Method " << method << " should include result";
    }
}

// ============================================================================
// Multiple requests tests
// ============================================================================

TEST_F(HandlersTest, HandlesMultipleSequentialRequests) {
    start_server_with_handlers();
    
    for (int i = 0; i < 10; ++i) {
        auto response = send_json_request("ping");
        EXPECT_TRUE(response["success"]) << "Request " << i << " should succeed";
    }
}

TEST_F(HandlersTest, HandlesMixedRequests) {
    start_server_with_handlers();
    
    EXPECT_TRUE(send_json_request("ping")["success"]);
    EXPECT_TRUE(send_json_request("version")["success"]);
    EXPECT_TRUE(send_json_request("config.get")["success"]);
    EXPECT_TRUE(send_json_request("ping")["success"]);
    EXPECT_FALSE(send_json_request("unknown")["success"]);
    EXPECT_TRUE(send_json_request("version")["success"]);
}

// ============================================================================
// Concurrent handler tests
// ============================================================================

TEST_F(HandlersTest, HandlesConcurrentRequests) {
    start_server_with_handlers();
    
    std::atomic<int> success_count{0};
    std::vector<std::thread> threads;
    
    for (int t = 0; t < 5; ++t) {
        threads.emplace_back([&, t]() {
            std::vector<std::string> methods = {"ping", "version", "config.get"};
            for (int i = 0; i < 10; ++i) {
                auto response = send_json_request(methods[i % methods.size()]);
                if (response["success"]) {
                    success_count++;
                }
            }
        });
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
    
    // Most requests should succeed
    EXPECT_GT(success_count.load(), 40);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
