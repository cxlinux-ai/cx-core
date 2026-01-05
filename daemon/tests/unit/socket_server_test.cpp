#include <gtest/gtest.h>
#include "socket_server.h"
#include "ipc_protocol.h"
#include "alert_manager.h"
#include <thread>
#include <chrono>

using namespace cortex::daemon;

// ============================================================================
// Socket Server Tests
// ============================================================================

class SocketServerTest : public ::testing::Test {
protected:
    SocketServer server;

    void SetUp() override {
        // Use a test socket path
    }

    void TearDown() override {
        if (server.is_running()) {
            server.stop();
        }
    }
};

TEST_F(SocketServerTest, CanStartServer) {
    EXPECT_TRUE(server.start());
    EXPECT_TRUE(server.is_running());
}

TEST_F(SocketServerTest, CanStopServer) {
    ASSERT_TRUE(server.start());
    server.stop();
    EXPECT_FALSE(server.is_running());
}

TEST_F(SocketServerTest, SocketFileCreated) {
    ASSERT_TRUE(server.start());
    // Verify socket file exists at the expected path
    std::string socket_path = server.get_socket_path();
    // TODO: Check file exists
}

TEST_F(SocketServerTest, MultipleStartsIdempotent) {
    EXPECT_TRUE(server.start());
    EXPECT_TRUE(server.start());  // Second start should be safe
    EXPECT_TRUE(server.is_running());
}

// ============================================================================
// IPC Protocol Tests
// ============================================================================

class IPCProtocolTest : public ::testing::Test {
};

TEST_F(IPCProtocolTest, ParseStatusCommand) {
    std::string request = R"({"command":"status"})";
    auto [cmd_type, params] = IPCProtocol::parse_request(request);
    EXPECT_EQ(cmd_type, CommandType::STATUS);
}

TEST_F(IPCProtocolTest, ParseHealthCommand) {
    std::string request = R"({"command":"health"})";
    auto [cmd_type, params] = IPCProtocol::parse_request(request);
    EXPECT_EQ(cmd_type, CommandType::HEALTH);
}

TEST_F(IPCProtocolTest, ParseAlertsCommand) {
    std::string request = R"({"command":"alerts"})";
    auto [cmd_type, params] = IPCProtocol::parse_request(request);
    EXPECT_EQ(cmd_type, CommandType::ALERTS);
}

TEST_F(IPCProtocolTest, ParseInvalidCommand) {
    std::string request = R"({"command":"invalid_command"})";
    auto [cmd_type, params] = IPCProtocol::parse_request(request);
    EXPECT_EQ(cmd_type, CommandType::UNKNOWN);
}

TEST_F(IPCProtocolTest, BuildStatusResponse) {
    HealthSnapshot health;
    health.timestamp = std::chrono::system_clock::now();
    health.cpu_usage = 50.5;
    health.memory_usage = 35.2;

    std::string response = IPCProtocol::build_status_response(health);
    EXPECT_FALSE(response.empty());
    EXPECT_NE(response.find("ok"), std::string::npos);
}

TEST_F(IPCProtocolTest, BuildErrorResponse) {
    std::string error_msg = "Test error";
    std::string response = IPCProtocol::build_error_response(error_msg);

    EXPECT_FALSE(response.empty());
    EXPECT_NE(response.find("error"), std::string::npos);
    EXPECT_NE(response.find(error_msg), std::string::npos);
}

// ============================================================================
// Alert Manager Tests
// ============================================================================

class AlertManagerTest : public ::testing::Test {
protected:
    AlertManagerImpl alert_mgr;
};

TEST_F(AlertManagerTest, CreateAlert) {
    std::string alert_id = alert_mgr.create_alert(
        AlertSeverity::WARNING,
        AlertType::DISK_USAGE,
        "High Disk Usage",
        "Disk usage at 85%"
    );

    EXPECT_FALSE(alert_id.empty());
}

TEST_F(AlertManagerTest, GetActiveAlerts) {
    alert_mgr.create_alert(
        AlertSeverity::INFO,
        AlertType::APT_UPDATES,
        "APT Updates Available",
        "5 packages can be updated"
    );

    auto alerts = alert_mgr.get_active_alerts();
    EXPECT_EQ(alerts.size(), 1);
}

TEST_F(AlertManagerTest, GetAlertsBySeverity) {
    alert_mgr.create_alert(AlertSeverity::WARNING, AlertType::DISK_USAGE, "High Disk", "");
    alert_mgr.create_alert(AlertSeverity::ERROR, AlertType::SYSTEM_ERROR, "System Error", "");
    alert_mgr.create_alert(AlertSeverity::WARNING, AlertType::MEMORY_USAGE, "High Memory", "");

    auto warnings = alert_mgr.get_alerts_by_severity(AlertSeverity::WARNING);
    EXPECT_EQ(warnings.size(), 2);

    auto errors = alert_mgr.get_alerts_by_severity(AlertSeverity::ERROR);
    EXPECT_EQ(errors.size(), 1);
}

TEST_F(AlertManagerTest, GetAlertsByType) {
    alert_mgr.create_alert(AlertSeverity::INFO, AlertType::APT_UPDATES, "Title1", "");
    alert_mgr.create_alert(AlertSeverity::INFO, AlertType::APT_UPDATES, "Title2", "");
    alert_mgr.create_alert(AlertSeverity::INFO, AlertType::DISK_USAGE, "Title3", "");

    auto apt_alerts = alert_mgr.get_alerts_by_type(AlertType::APT_UPDATES);
    EXPECT_EQ(apt_alerts.size(), 2);

    auto disk_alerts = alert_mgr.get_alerts_by_type(AlertType::DISK_USAGE);
    EXPECT_EQ(disk_alerts.size(), 1);
}

TEST_F(AlertManagerTest, AcknowledgeAlert) {
    std::string alert_id = alert_mgr.create_alert(
        AlertSeverity::WARNING,
        AlertType::MEMORY_USAGE,
        "High Memory",
        ""
    );

    EXPECT_TRUE(alert_mgr.acknowledge_alert(alert_id));

    auto active = alert_mgr.get_active_alerts();
    EXPECT_EQ(active.size(), 0);
}

TEST_F(AlertManagerTest, ClearAcknowledgedAlerts) {
    std::string id1 = alert_mgr.create_alert(
        AlertSeverity::INFO,
        AlertType::APT_UPDATES,
        "Title1",
        ""
    );
    std::string id2 = alert_mgr.create_alert(
        AlertSeverity::INFO,
        AlertType::APT_UPDATES,
        "Title2",
        ""
    );

    alert_mgr.acknowledge_alert(id1);
    alert_mgr.acknowledge_alert(id2);

    EXPECT_EQ(alert_mgr.get_alert_count(), 2);

    alert_mgr.clear_acknowledged_alerts();
    EXPECT_EQ(alert_mgr.get_alert_count(), 0);
}

TEST_F(AlertManagerTest, ExportAlertsJson) {
    alert_mgr.create_alert(
        AlertSeverity::WARNING,
        AlertType::DISK_USAGE,
        "High Disk",
        "Disk 85%"
    );

    auto json_alerts = alert_mgr.export_alerts_json();
    EXPECT_TRUE(json_alerts.is_array());
    EXPECT_GT(json_alerts.size(), 0);
}

// ============================================================================
// Common Utilities Tests
// ============================================================================

class CommonUtilitiesTest : public ::testing::Test {
};

TEST_F(CommonUtilitiesTest, SeverityToString) {
    EXPECT_EQ(to_string(AlertSeverity::INFO), "info");
    EXPECT_EQ(to_string(AlertSeverity::WARNING), "warning");
    EXPECT_EQ(to_string(AlertSeverity::ERROR), "error");
    EXPECT_EQ(to_string(AlertSeverity::CRITICAL), "critical");
}

TEST_F(CommonUtilitiesTest, SeverityFromString) {
    EXPECT_EQ(severity_from_string("info"), AlertSeverity::INFO);
    EXPECT_EQ(severity_from_string("warning"), AlertSeverity::WARNING);
    EXPECT_EQ(severity_from_string("ERROR"), AlertSeverity::ERROR);
    EXPECT_EQ(severity_from_string("CRITICAL"), AlertSeverity::CRITICAL);
}

TEST_F(CommonUtilitiesTest, AlertTypeToString) {
    EXPECT_EQ(to_string(AlertType::APT_UPDATES), "apt_updates");
    EXPECT_EQ(to_string(AlertType::DISK_USAGE), "disk_usage");
    EXPECT_EQ(to_string(AlertType::MEMORY_USAGE), "memory_usage");
    EXPECT_EQ(to_string(AlertType::CVE_FOUND), "cve_found");
}

TEST_F(CommonUtilitiesTest, CommandFromString) {
    EXPECT_EQ(command_from_string("status"), CommandType::STATUS);
    EXPECT_EQ(command_from_string("alerts"), CommandType::ALERTS);
    EXPECT_EQ(command_from_string("health"), CommandType::HEALTH);
    EXPECT_EQ(command_from_string("shutdown"), CommandType::SHUTDOWN);
    EXPECT_EQ(command_from_string("unknown"), CommandType::UNKNOWN);
}

// ============================================================================
// Main
// ============================================================================

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
