/**
 * @file test_ipc_server.cpp
 * @brief Integration tests for IPCServer
 */

#include <gtest/gtest.h>
#include <thread>
#include <chrono>
#include <fstream>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <filesystem>
#include "cortexd/ipc/server.h"
#include "cortexd/ipc/protocol.h"
#include "cortexd/logger.h"

namespace fs = std::filesystem;

class IPCServerTest : public ::testing::Test {
protected:
    void SetUp() override {
        cortexd::Logger::init(cortexd::LogLevel::ERROR, false);
        
        // Create a unique socket path for each test
        socket_path_ = "/tmp/cortexd_test_" + std::to_string(getpid()) + ".sock";
        
        // Clean up any existing socket
        if (fs::exists(socket_path_)) {
            fs::remove(socket_path_);
        }
    }
    
    void TearDown() override {
        // Stop server if running
        if (server_) {
            server_->stop();
            server_.reset();
        }
        
        // Clean up socket file
        if (fs::exists(socket_path_)) {
            fs::remove(socket_path_);
        }
        
        cortexd::Logger::shutdown();
    }
    
    // Create and start the server
    void start_server(int max_requests_per_sec = 100) {
        server_ = std::make_unique<cortexd::IPCServer>(socket_path_, max_requests_per_sec);
        ASSERT_TRUE(server_->start());
        
        // Give server time to start
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    
    // Connect to the server and send a request
    std::string send_request(const std::string& request) {
        int sock = socket(AF_UNIX, SOCK_STREAM, 0);
        EXPECT_NE(sock, -1);
        
        struct sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, socket_path_.c_str(), sizeof(addr.sun_path) - 1);
        
        int result = connect(sock, (struct sockaddr*)&addr, sizeof(addr));
        if (result == -1) {
            close(sock);
            return "";
        }
        
        // Send request
        send(sock, request.c_str(), request.length(), 0);
        
        // Receive response
        char buffer[65536];
        ssize_t bytes = recv(sock, buffer, sizeof(buffer) - 1, 0);
        close(sock);
        
        if (bytes <= 0) {
            return "";
        }
        
        buffer[bytes] = '\0';
        return std::string(buffer);
    }
    
    std::string socket_path_;
    std::unique_ptr<cortexd::IPCServer> server_;
};

// ============================================================================
// Server lifecycle tests
// ============================================================================

TEST_F(IPCServerTest, StartsSuccessfully) {
    server_ = std::make_unique<cortexd::IPCServer>(socket_path_);
    
    EXPECT_TRUE(server_->start());
    EXPECT_TRUE(server_->is_running());
    EXPECT_TRUE(server_->is_healthy());
    
    // Socket file should exist
    EXPECT_TRUE(fs::exists(socket_path_));
}

TEST_F(IPCServerTest, StopsCleanly) {
    start_server();
    
    EXPECT_TRUE(server_->is_running());
    
    server_->stop();
    
    EXPECT_FALSE(server_->is_running());
    // Socket file should be cleaned up
    EXPECT_FALSE(fs::exists(socket_path_));
}

TEST_F(IPCServerTest, CanRestartAfterStop) {
    start_server();
    server_->stop();
    
    // Start again
    EXPECT_TRUE(server_->start());
    EXPECT_TRUE(server_->is_running());
}

TEST_F(IPCServerTest, StartTwiceReturnsTrue) {
    start_server();
    
    // Starting again should return true (already running)
    EXPECT_TRUE(server_->start());
}

TEST_F(IPCServerTest, StopTwiceIsSafe) {
    start_server();
    
    server_->stop();
    server_->stop();  // Should not crash
    
    EXPECT_FALSE(server_->is_running());
}

// ============================================================================
// Handler registration tests
// ============================================================================

TEST_F(IPCServerTest, RegisterHandlerWorks) {
    start_server();
    
    // Register a simple handler
    server_->register_handler("test.echo", [](const cortexd::Request& req) {
        return cortexd::Response::ok(req.params);
    });
    
    // Send a request
    std::string request = R"({"method": "test.echo", "params": {"message": "hello"}})";
    std::string response = send_request(request);
    
    ASSERT_FALSE(response.empty());
    
    auto json = cortexd::json::parse(response);
    EXPECT_TRUE(json["success"]);
    EXPECT_EQ(json["result"]["message"], "hello");
}

TEST_F(IPCServerTest, UnknownMethodReturnsError) {
    start_server();
    
    std::string request = R"({"method": "unknown.method"})";
    std::string response = send_request(request);
    
    ASSERT_FALSE(response.empty());
    
    auto json = cortexd::json::parse(response);
    EXPECT_FALSE(json["success"]);
    EXPECT_EQ(json["error"]["code"], cortexd::ErrorCodes::METHOD_NOT_FOUND);
}

TEST_F(IPCServerTest, InvalidJsonReturnsParseError) {
    start_server();
    
    std::string request = "not valid json";
    std::string response = send_request(request);
    
    ASSERT_FALSE(response.empty());
    
    auto json = cortexd::json::parse(response);
    EXPECT_FALSE(json["success"]);
    EXPECT_EQ(json["error"]["code"], cortexd::ErrorCodes::PARSE_ERROR);
}

TEST_F(IPCServerTest, MissingMethodReturnsParseError) {
    start_server();
    
    std::string request = R"({"params": {"key": "value"}})";
    std::string response = send_request(request);
    
    ASSERT_FALSE(response.empty());
    
    auto json = cortexd::json::parse(response);
    EXPECT_FALSE(json["success"]);
}

// ============================================================================
// Rate limiting tests
// ============================================================================

TEST_F(IPCServerTest, RateLimitingWorks) {
    // Create server with low rate limit
    server_ = std::make_unique<cortexd::IPCServer>(socket_path_, 3);
    server_->register_handler("ping", [](const cortexd::Request&) {
        return cortexd::Response::ok({{"pong", true}});
    });
    ASSERT_TRUE(server_->start());
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    
    // First 3 requests should succeed
    for (int i = 0; i < 3; ++i) {
        std::string response = send_request(R"({"method": "ping"})");
        auto json = cortexd::json::parse(response);
        EXPECT_TRUE(json["success"]) << "Request " << i << " should succeed";
    }
    
    // 4th request should be rate limited
    std::string response = send_request(R"({"method": "ping"})");
    auto json = cortexd::json::parse(response);
    EXPECT_FALSE(json["success"]);
    EXPECT_EQ(json["error"]["code"], cortexd::ErrorCodes::RATE_LIMITED);
}

// ============================================================================
// Connection counting tests
// ============================================================================

TEST_F(IPCServerTest, TracksConnectionsServed) {
    start_server();
    server_->register_handler("ping", [](const cortexd::Request&) {
        return cortexd::Response::ok({{"pong", true}});
    });
    
    EXPECT_EQ(server_->connections_served(), 0);
    
    // Make some requests
    for (int i = 0; i < 5; ++i) {
        send_request(R"({"method": "ping"})");
    }
    
    // Give time for connections to be processed
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    EXPECT_EQ(server_->connections_served(), 5);
}

// ============================================================================
// Concurrent connection tests
// ============================================================================

TEST_F(IPCServerTest, HandlesConcurrentConnections) {
    start_server();
    
    std::atomic<int> success_count{0};
    server_->register_handler("ping", [&](const cortexd::Request&) {
        return cortexd::Response::ok({{"pong", true}});
    });
    
    // Launch multiple threads making requests
    std::vector<std::thread> threads;
    for (int t = 0; t < 5; ++t) {
        threads.emplace_back([&]() {
            for (int i = 0; i < 10; ++i) {
                std::string response = send_request(R"({"method": "ping"})");
                if (!response.empty()) {
                    auto json = cortexd::json::parse(response);
                    if (json["success"]) {
                        success_count++;
                    }
                }
            }
        });
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
    
    // Most requests should succeed (some might fail due to timing)
    EXPECT_GT(success_count.load(), 30);
}

// ============================================================================
// Handler exception tests
// ============================================================================

TEST_F(IPCServerTest, HandlerExceptionReturnsInternalError) {
    start_server();
    
    server_->register_handler("throw", [](const cortexd::Request&) -> cortexd::Response {
        throw std::runtime_error("Test exception");
    });
    
    std::string response = send_request(R"({"method": "throw"})");
    
    ASSERT_FALSE(response.empty());
    
    auto json = cortexd::json::parse(response);
    EXPECT_FALSE(json["success"]);
    EXPECT_EQ(json["error"]["code"], cortexd::ErrorCodes::INTERNAL_ERROR);
}

// ============================================================================
// Socket path tests
// ============================================================================

TEST_F(IPCServerTest, CreatesParentDirectoryIfNeeded) {
    std::string nested_path = "/tmp/cortexd_test_nested_" + std::to_string(getpid()) + "/test.sock";
    
    // Ensure parent doesn't exist
    fs::remove_all(fs::path(nested_path).parent_path());
    
    auto server = std::make_unique<cortexd::IPCServer>(nested_path);
    EXPECT_TRUE(server->start());
    EXPECT_TRUE(fs::exists(nested_path));
    
    server->stop();
    fs::remove_all(fs::path(nested_path).parent_path());
}

TEST_F(IPCServerTest, RemovesExistingSocketOnStart) {
    // Create a file at the socket path
    std::ofstream(socket_path_) << "dummy";
    EXPECT_TRUE(fs::exists(socket_path_));
    
    // Server should remove it and create a socket
    start_server();
    
    EXPECT_TRUE(server_->is_running());
}

// ============================================================================
// Response format tests
// ============================================================================

TEST_F(IPCServerTest, ResponseIncludesTimestamp) {
    start_server();
    server_->register_handler("ping", [](const cortexd::Request&) {
        return cortexd::Response::ok({{"pong", true}});
    });
    
    std::string response = send_request(R"({"method": "ping"})");
    
    auto json = cortexd::json::parse(response);
    EXPECT_TRUE(json.contains("timestamp"));
    EXPECT_TRUE(json["timestamp"].is_number());
}

// ============================================================================
// Edge case: Concurrent handler registration tests
// ============================================================================

TEST_F(IPCServerTest, ConcurrentHandlerRegistration) {
    start_server();
    
    // Register handlers from multiple threads concurrently
    std::vector<std::thread> threads;
    std::atomic<int> success_count{0};
    
    for (int t = 0; t < 10; ++t) {
        threads.emplace_back([&, t]() {
            std::string method = "test.method" + std::to_string(t);
            server_->register_handler(method, [](const cortexd::Request&) {
                return cortexd::Response::ok({{"registered", true}});
            });
            success_count++;
        });
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
    
    EXPECT_EQ(success_count.load(), 10);
    
    // Verify all handlers work
    for (int t = 0; t < 10; ++t) {
        std::string method = "test.method" + std::to_string(t);
        std::string request = R"({"method": ")" + method + R"("})";
        std::string response = send_request(request);
        auto json = cortexd::json::parse(response);
        EXPECT_TRUE(json["success"]) << "Handler " << method << " should work";
    }
}

// ============================================================================
// Edge case: Malformed JSON tests
// ============================================================================

TEST_F(IPCServerTest, HandlesDuplicateJsonKeys) {
    start_server();
    server_->register_handler("ping", [](const cortexd::Request&) {
        return cortexd::Response::ok({{"pong", true}});
    });
    
    // JSON with duplicate keys - nlohmann/json keeps last value
    std::string request = R"({"method": "ping", "method": "unknown"})";
    std::string response = send_request(request);
    
    auto json = cortexd::json::parse(response);
    // Should use last "method" value, so unknown method
    EXPECT_FALSE(json["success"]);
}

TEST_F(IPCServerTest, HandlesUtf8InMethodName) {
    start_server();
    
    // Register handler with UTF-8 in method name
    std::string utf8_method = "test.方法";
    server_->register_handler(utf8_method, [](const cortexd::Request&) {
        return cortexd::Response::ok({{"utf8", true}});
    });
    
    // Send request with UTF-8 method
    cortexd::json request;
    request["method"] = utf8_method;
    std::string response = send_request(request.dump());
    
    auto json = cortexd::json::parse(response);
    EXPECT_TRUE(json["success"]);
}

TEST_F(IPCServerTest, HandlesInvalidUtf8Sequence) {
    start_server();
    
    // Send request with invalid UTF-8 bytes
    // nlohmann/json should handle this gracefully
    std::string invalid_utf8 = "{\"method\": \"test\", \"params\": {\"data\": \"\xFF\xFE\"}}";
    std::string response = send_request(invalid_utf8);
    
    // Should either parse (if JSON library is lenient) or return parse error
    auto json = cortexd::json::parse(response);
    // Either way, should not crash
    EXPECT_TRUE(json.contains("success") || json.contains("error"));
}

// ============================================================================
// Edge case: Socket cleanup on crash tests
// ============================================================================

TEST_F(IPCServerTest, SocketCleanupOnStop) {
    start_server();
    
    // Verify socket exists
    EXPECT_TRUE(fs::exists(socket_path_));
    
    // Stop server (simulates crash/clean shutdown)
    server_->stop();
    
    // Socket should be cleaned up
    EXPECT_FALSE(fs::exists(socket_path_));
}

TEST_F(IPCServerTest, SocketCleanupOnDestruction) {
    {
        auto server = std::make_unique<cortexd::IPCServer>(socket_path_);
        ASSERT_TRUE(server->start());
        EXPECT_TRUE(fs::exists(socket_path_));
        
        // Server goes out of scope (simulates crash)
        // Destructor should clean up socket
    }
    
    // Socket should be cleaned up after destruction
    EXPECT_FALSE(fs::exists(socket_path_));
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
