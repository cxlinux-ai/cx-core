/**
 * @file test_common.cpp
 * @brief Unit tests for common.h constants and types (PR1 scope only)
 * 
 * PR1 includes: Core daemon, IPC server, config management
 */

#include <gtest/gtest.h>
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
// Startup time target (PR1 - daemon startup performance)
// ============================================================================

TEST_F(CommonTest, StartupTimeTargetIsDefined) {
    EXPECT_GT(cortexd::STARTUP_TIME_MS, 0);
    // Should be reasonable (less than 10 seconds)
    EXPECT_LT(cortexd::STARTUP_TIME_MS, 10000);
}

// ============================================================================
// Clock type alias (PR1 - used in IPC protocol)
// ============================================================================

TEST_F(CommonTest, ClockTypeAliasIsDefined) {
    // Verify Clock is a valid type alias
    cortexd::Clock::time_point now = cortexd::Clock::now();
    EXPECT_GT(now.time_since_epoch().count(), 0);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
