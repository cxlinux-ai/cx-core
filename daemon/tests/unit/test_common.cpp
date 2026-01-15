/**
 * @file test_common.cpp
 * @brief Unit tests for common.h constants and types (PR1 scope only)
 * 
 * PR1 includes: Core daemon, IPC server, config management
 * PR2 adds: Monitoring, alerts (AlertSeverity, AlertType, HealthSnapshot)
 * PR3 adds: LLM integration
 */

#include <gtest/gtest.h>
#include <set>
#include "cortexd/common.h"

class CommonTest : public ::testing::Test {
protected:
    void SetUp() override {}
    void TearDown() override {}
};

// ============================================================================
// Version and Name constants (PR1)
// ============================================================================

TEST_F(CommonTest, VersionIsDefined) {
    EXPECT_NE(cortexd::VERSION, nullptr);
    EXPECT_STRNE(cortexd::VERSION, "");
}

TEST_F(CommonTest, NameIsDefined) {
    EXPECT_NE(cortexd::NAME, nullptr);
    EXPECT_STREQ(cortexd::NAME, "cortexd");
}

// ============================================================================
// Socket constants (PR1 - used by IPC server)
// ============================================================================

TEST_F(CommonTest, DefaultSocketPathIsDefined) {
    EXPECT_NE(cortexd::DEFAULT_SOCKET_PATH, nullptr);
    EXPECT_STREQ(cortexd::DEFAULT_SOCKET_PATH, "/run/cortex/cortex.sock");
}

TEST_F(CommonTest, SocketBacklogIsPositive) {
    EXPECT_GT(cortexd::SOCKET_BACKLOG, 0);
}

TEST_F(CommonTest, SocketTimeoutIsPositive) {
    EXPECT_GT(cortexd::SOCKET_TIMEOUT_MS, 0);
}

TEST_F(CommonTest, MaxMessageSizeIsPositive) {
    EXPECT_GT(cortexd::MAX_MESSAGE_SIZE, 0);
    // Should be at least 1KB for reasonable messages
    EXPECT_GE(cortexd::MAX_MESSAGE_SIZE, 1024);
}

// ============================================================================
// CommandType enum tests (PR1 - shutdown and config_reload are available)
// ============================================================================

TEST_F(CommonTest, CommandTypeEnumValuesAreDistinct) {
    std::set<int> values;
    values.insert(static_cast<int>(cortexd::CommandType::STATUS));
    values.insert(static_cast<int>(cortexd::CommandType::ALERTS));
    values.insert(static_cast<int>(cortexd::CommandType::SHUTDOWN));
    values.insert(static_cast<int>(cortexd::CommandType::CONFIG_RELOAD));
    values.insert(static_cast<int>(cortexd::CommandType::HEALTH));
    values.insert(static_cast<int>(cortexd::CommandType::UNKNOWN));
    
    EXPECT_EQ(values.size(), 6);
}

TEST_F(CommonTest, CommandTypeUnknownExists) {
    // UNKNOWN should be a valid enum value for unrecognized commands
    cortexd::CommandType cmd = cortexd::CommandType::UNKNOWN;
    EXPECT_EQ(cmd, cortexd::CommandType::UNKNOWN);
}

TEST_F(CommonTest, CommandTypeShutdownExists) {
    // SHUTDOWN is available in PR1
    cortexd::CommandType cmd = cortexd::CommandType::SHUTDOWN;
    EXPECT_EQ(cmd, cortexd::CommandType::SHUTDOWN);
}

TEST_F(CommonTest, CommandTypeConfigReloadExists) {
    // CONFIG_RELOAD is available in PR1
    cortexd::CommandType cmd = cortexd::CommandType::CONFIG_RELOAD;
    EXPECT_EQ(cmd, cortexd::CommandType::CONFIG_RELOAD);
}

// ============================================================================
// Memory constraints (PR1 - daemon memory footprint targets)
// ============================================================================

TEST_F(CommonTest, IdleMemoryConstraintIsDefined) {
    EXPECT_GT(cortexd::IDLE_MEMORY_MB, 0);
}

TEST_F(CommonTest, ActiveMemoryConstraintIsDefined) {
    EXPECT_GT(cortexd::ACTIVE_MEMORY_MB, 0);
}

TEST_F(CommonTest, ActiveMemoryGreaterThanIdle) {
    EXPECT_GT(cortexd::ACTIVE_MEMORY_MB, cortexd::IDLE_MEMORY_MB);
}

// ============================================================================
// Startup time target (PR1 - daemon startup performance)
// ============================================================================

TEST_F(CommonTest, StartupTimeTargetIsDefined) {
    EXPECT_GT(cortexd::STARTUP_TIME_MS, 0);
    // Should be reasonable (less than 10 seconds)
    EXPECT_LT(cortexd::STARTUP_TIME_MS, 10000);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
