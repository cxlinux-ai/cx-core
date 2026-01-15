/**
 * @file test_protocol.cpp
 * @brief Unit tests for IPC protocol (Request/Response)
 */

#include <gtest/gtest.h>
#include "cortexd/ipc/protocol.h"
#include "cortexd/logger.h"

class ProtocolTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Initialize logger in non-journald mode for tests
        cortexd::Logger::init(cortexd::LogLevel::ERROR, false);
    }
    
    void TearDown() override {
        cortexd::Logger::shutdown();
    }
};

// ============================================================================
// Request::parse() tests
// ============================================================================

TEST_F(ProtocolTest, ParseValidRequestWithMethod) {
    std::string json = R"({"method": "ping"})";
    
    auto result = cortexd::Request::parse(json);
    
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->method, "ping");
    EXPECT_TRUE(result->params.empty());
    EXPECT_FALSE(result->id.has_value());
}

TEST_F(ProtocolTest, ParseValidRequestWithParams) {
    std::string json = R"({
        "method": "config.get",
        "params": {"key": "socket_path"}
    })";
    
    auto result = cortexd::Request::parse(json);
    
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->method, "config.get");
    EXPECT_TRUE(result->params.contains("key"));
    EXPECT_EQ(result->params["key"], "socket_path");
}

TEST_F(ProtocolTest, ParseValidRequestWithStringId) {
    std::string json = R"({
        "method": "version",
        "id": "request-123"
    })";
    
    auto result = cortexd::Request::parse(json);
    
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->method, "version");
    ASSERT_TRUE(result->id.has_value());
    EXPECT_EQ(result->id.value(), "request-123");
}

TEST_F(ProtocolTest, ParseValidRequestWithNumericId) {
    std::string json = R"({
        "method": "version",
        "id": 42
    })";
    
    auto result = cortexd::Request::parse(json);
    
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->method, "version");
    ASSERT_TRUE(result->id.has_value());
    EXPECT_EQ(result->id.value(), "42");
}

TEST_F(ProtocolTest, ParseReturnsNulloptForMissingMethod) {
    std::string json = R"({"params": {"key": "value"}})";
    
    auto result = cortexd::Request::parse(json);
    
    EXPECT_FALSE(result.has_value());
}

TEST_F(ProtocolTest, ParseReturnsNulloptForNonStringMethod) {
    std::string json = R"({"method": 123})";
    
    auto result = cortexd::Request::parse(json);
    
    EXPECT_FALSE(result.has_value());
}

TEST_F(ProtocolTest, ParseReturnsNulloptForInvalidJson) {
    std::string json = "this is not json";
    
    auto result = cortexd::Request::parse(json);
    
    EXPECT_FALSE(result.has_value());
}

TEST_F(ProtocolTest, ParseReturnsNulloptForEmptyString) {
    std::string json = "";
    
    auto result = cortexd::Request::parse(json);
    
    EXPECT_FALSE(result.has_value());
}

TEST_F(ProtocolTest, ParseReturnsNulloptForMalformedJson) {
    std::string json = R"({"method": "ping")";  // Missing closing brace
    
    auto result = cortexd::Request::parse(json);
    
    EXPECT_FALSE(result.has_value());
}

TEST_F(ProtocolTest, ParseHandlesEmptyParams) {
    std::string json = R"({
        "method": "ping",
        "params": {}
    })";
    
    auto result = cortexd::Request::parse(json);
    
    ASSERT_TRUE(result.has_value());
    EXPECT_TRUE(result->params.empty());
}

TEST_F(ProtocolTest, ParseHandlesComplexParams) {
    std::string json = R"({
        "method": "test",
        "params": {
            "string": "value",
            "number": 42,
            "boolean": true,
            "array": [1, 2, 3],
            "nested": {"inner": "data"}
        }
    })";
    
    auto result = cortexd::Request::parse(json);
    
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->params["string"], "value");
    EXPECT_EQ(result->params["number"], 42);
    EXPECT_EQ(result->params["boolean"], true);
    EXPECT_EQ(result->params["array"].size(), 3);
    EXPECT_EQ(result->params["nested"]["inner"], "data");
}

// ============================================================================
// Request::to_json() tests
// ============================================================================

TEST_F(ProtocolTest, RequestToJsonProducesValidJson) {
    cortexd::Request req;
    req.method = "ping";
    req.params = cortexd::json::object();
    
    std::string json_str = req.to_json();
    
    // Parse it back
    auto parsed = cortexd::json::parse(json_str);
    EXPECT_EQ(parsed["method"], "ping");
}

TEST_F(ProtocolTest, RequestToJsonIncludesParams) {
    cortexd::Request req;
    req.method = "test";
    req.params = {{"key", "value"}};
    
    std::string json_str = req.to_json();
    
    auto parsed = cortexd::json::parse(json_str);
    EXPECT_EQ(parsed["method"], "test");
    EXPECT_EQ(parsed["params"]["key"], "value");
}

TEST_F(ProtocolTest, RequestToJsonIncludesId) {
    cortexd::Request req;
    req.method = "test";
    req.params = cortexd::json::object();
    req.id = "my-id";
    
    std::string json_str = req.to_json();
    
    auto parsed = cortexd::json::parse(json_str);
    EXPECT_EQ(parsed["id"], "my-id");
}

// ============================================================================
// Response::ok() tests
// ============================================================================

TEST_F(ProtocolTest, ResponseOkCreatesSuccessResponse) {
    auto resp = cortexd::Response::ok();
    
    EXPECT_TRUE(resp.success);
    EXPECT_TRUE(resp.error.empty());
    EXPECT_EQ(resp.error_code, 0);
}

TEST_F(ProtocolTest, ResponseOkIncludesResult) {
    auto resp = cortexd::Response::ok({{"key", "value"}, {"number", 42}});
    
    EXPECT_TRUE(resp.success);
    EXPECT_EQ(resp.result["key"], "value");
    EXPECT_EQ(resp.result["number"], 42);
}

TEST_F(ProtocolTest, ResponseOkWithEmptyResult) {
    auto resp = cortexd::Response::ok(cortexd::json::object());
    
    EXPECT_TRUE(resp.success);
    EXPECT_TRUE(resp.result.empty());
}

// ============================================================================
// Response::err() tests
// ============================================================================

TEST_F(ProtocolTest, ResponseErrCreatesErrorResponse) {
    auto resp = cortexd::Response::err("Something went wrong");
    
    EXPECT_FALSE(resp.success);
    EXPECT_EQ(resp.error, "Something went wrong");
    EXPECT_EQ(resp.error_code, -1);  // Default code
}

TEST_F(ProtocolTest, ResponseErrWithCustomCode) {
    auto resp = cortexd::Response::err("Not found", cortexd::ErrorCodes::METHOD_NOT_FOUND);
    
    EXPECT_FALSE(resp.success);
    EXPECT_EQ(resp.error, "Not found");
    EXPECT_EQ(resp.error_code, cortexd::ErrorCodes::METHOD_NOT_FOUND);
}

TEST_F(ProtocolTest, ResponseErrWithAllErrorCodes) {
    // Test standard JSON-RPC error codes
    auto parse_err = cortexd::Response::err("Parse error", cortexd::ErrorCodes::PARSE_ERROR);
    EXPECT_EQ(parse_err.error_code, -32700);
    
    auto invalid_req = cortexd::Response::err("Invalid", cortexd::ErrorCodes::INVALID_REQUEST);
    EXPECT_EQ(invalid_req.error_code, -32600);
    
    auto method_not_found = cortexd::Response::err("Not found", cortexd::ErrorCodes::METHOD_NOT_FOUND);
    EXPECT_EQ(method_not_found.error_code, -32601);
    
    auto invalid_params = cortexd::Response::err("Invalid params", cortexd::ErrorCodes::INVALID_PARAMS);
    EXPECT_EQ(invalid_params.error_code, -32602);
    
    auto internal = cortexd::Response::err("Internal", cortexd::ErrorCodes::INTERNAL_ERROR);
    EXPECT_EQ(internal.error_code, -32603);
    
    // Test custom error codes
    auto rate_limited = cortexd::Response::err("Rate limited", cortexd::ErrorCodes::RATE_LIMITED);
    EXPECT_EQ(rate_limited.error_code, 102);
    
    auto config_error = cortexd::Response::err("Config error", cortexd::ErrorCodes::CONFIG_ERROR);
    EXPECT_EQ(config_error.error_code, 104);
}

// ============================================================================
// Response::to_json() tests
// ============================================================================

TEST_F(ProtocolTest, ResponseToJsonProducesValidJson) {
    auto resp = cortexd::Response::ok({{"pong", true}});
    
    std::string json_str = resp.to_json();
    
    auto parsed = cortexd::json::parse(json_str);
    EXPECT_TRUE(parsed["success"]);
    EXPECT_TRUE(parsed.contains("timestamp"));
    EXPECT_TRUE(parsed.contains("result"));
    EXPECT_EQ(parsed["result"]["pong"], true);
}

TEST_F(ProtocolTest, ResponseToJsonErrorFormat) {
    auto resp = cortexd::Response::err("Test error", 123);
    
    std::string json_str = resp.to_json();
    
    auto parsed = cortexd::json::parse(json_str);
    EXPECT_FALSE(parsed["success"]);
    EXPECT_TRUE(parsed.contains("error"));
    EXPECT_EQ(parsed["error"]["message"], "Test error");
    EXPECT_EQ(parsed["error"]["code"], 123);
}

TEST_F(ProtocolTest, ResponseToJsonIncludesTimestamp) {
    auto resp = cortexd::Response::ok();
    
    std::string json_str = resp.to_json();
    
    auto parsed = cortexd::json::parse(json_str);
    EXPECT_TRUE(parsed.contains("timestamp"));
    EXPECT_TRUE(parsed["timestamp"].is_number());
}

// ============================================================================
// Methods namespace tests (PR1 methods only)
// ============================================================================

TEST_F(ProtocolTest, PR1MethodConstantsAreDefined) {
    // PR1 available methods: ping, version, config.get, config.reload, shutdown
    EXPECT_STREQ(cortexd::Methods::PING, "ping");
    EXPECT_STREQ(cortexd::Methods::VERSION, "version");
    EXPECT_STREQ(cortexd::Methods::CONFIG_GET, "config.get");
    EXPECT_STREQ(cortexd::Methods::CONFIG_RELOAD, "config.reload");
    EXPECT_STREQ(cortexd::Methods::SHUTDOWN, "shutdown");
}

TEST_F(ProtocolTest, PR2MethodConstantsAreDefined) {
    // PR2 methods are defined in protocol.h but handlers not registered in PR1
    // These constants exist for forward compatibility
    EXPECT_STREQ(cortexd::Methods::STATUS, "status");
    EXPECT_STREQ(cortexd::Methods::HEALTH, "health");
    EXPECT_STREQ(cortexd::Methods::ALERTS, "alerts");
}

// ============================================================================
// Round-trip tests
// ============================================================================

TEST_F(ProtocolTest, RequestRoundTrip) {
    cortexd::Request original;
    original.method = "test.method";
    original.params = {{"param1", "value1"}, {"param2", 123}};
    original.id = "test-id-456";
    
    // Serialize
    std::string json_str = original.to_json();
    
    // Parse back
    auto parsed = cortexd::Request::parse(json_str);
    
    ASSERT_TRUE(parsed.has_value());
    EXPECT_EQ(parsed->method, original.method);
    EXPECT_EQ(parsed->params["param1"], original.params["param1"]);
    EXPECT_EQ(parsed->params["param2"], original.params["param2"]);
    EXPECT_EQ(parsed->id, original.id);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
