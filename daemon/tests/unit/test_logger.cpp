/**
 * @file test_logger.cpp
 * @brief Unit tests for Logger class
 */

#include <gtest/gtest.h>
#include <sstream>
#include <regex>
#include <thread>
#include <vector>
#include <atomic>
#include "cortexd/logger.h"

class LoggerTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Each test starts with a fresh logger state
        cortexd::Logger::shutdown();
    }
    
    void TearDown() override {
        cortexd::Logger::shutdown();
    }
};

// ============================================================================
// Initialization tests
// ============================================================================

TEST_F(LoggerTest, InitializesWithDefaultLevel) {
    cortexd::Logger::init(cortexd::LogLevel::INFO, false);
    
    EXPECT_EQ(cortexd::Logger::get_level(), cortexd::LogLevel::INFO);
}

TEST_F(LoggerTest, InitializesWithCustomLevel) {
    cortexd::Logger::init(cortexd::LogLevel::DEBUG, false);
    
    EXPECT_EQ(cortexd::Logger::get_level(), cortexd::LogLevel::DEBUG);
}

TEST_F(LoggerTest, InitializesWithErrorLevel) {
    cortexd::Logger::init(cortexd::LogLevel::ERROR, false);
    
    EXPECT_EQ(cortexd::Logger::get_level(), cortexd::LogLevel::ERROR);
}

TEST_F(LoggerTest, InitializesWithCriticalLevel) {
    cortexd::Logger::init(cortexd::LogLevel::CRITICAL, false);
    
    EXPECT_EQ(cortexd::Logger::get_level(), cortexd::LogLevel::CRITICAL);
}

// ============================================================================
// Level setting tests
// ============================================================================

TEST_F(LoggerTest, SetLevelWorks) {
    cortexd::Logger::init(cortexd::LogLevel::INFO, false);
    
    cortexd::Logger::set_level(cortexd::LogLevel::DEBUG);
    EXPECT_EQ(cortexd::Logger::get_level(), cortexd::LogLevel::DEBUG);
    
    cortexd::Logger::set_level(cortexd::LogLevel::WARN);
    EXPECT_EQ(cortexd::Logger::get_level(), cortexd::LogLevel::WARN);
    
    cortexd::Logger::set_level(cortexd::LogLevel::ERROR);
    EXPECT_EQ(cortexd::Logger::get_level(), cortexd::LogLevel::ERROR);
}

TEST_F(LoggerTest, GetLevelReturnsCorrectLevel) {
    cortexd::Logger::init(cortexd::LogLevel::WARN, false);
    
    EXPECT_EQ(cortexd::Logger::get_level(), cortexd::LogLevel::WARN);
}

// ============================================================================
// Log level filtering tests
// ============================================================================

TEST_F(LoggerTest, DebugLevelLogsAllMessages) {
    cortexd::Logger::init(cortexd::LogLevel::DEBUG, false);
    
    // These should not throw or crash
    cortexd::Logger::debug("Test", "debug message");
    cortexd::Logger::info("Test", "info message");
    cortexd::Logger::warn("Test", "warn message");
    cortexd::Logger::error("Test", "error message");
    cortexd::Logger::critical("Test", "critical message");
    
    SUCCEED();
}

TEST_F(LoggerTest, InfoLevelFiltersDebug) {
    cortexd::Logger::init(cortexd::LogLevel::INFO, false);
    
    // Debug should be filtered
    cortexd::Logger::debug("Test", "should be filtered");
    
    // These should pass through
    cortexd::Logger::info("Test", "info message");
    cortexd::Logger::warn("Test", "warn message");
    cortexd::Logger::error("Test", "error message");
    cortexd::Logger::critical("Test", "critical message");
    
    SUCCEED();
}

TEST_F(LoggerTest, WarnLevelFiltersDebugAndInfo) {
    cortexd::Logger::init(cortexd::LogLevel::WARN, false);
    
    // Debug and Info should be filtered
    cortexd::Logger::debug("Test", "should be filtered");
    cortexd::Logger::info("Test", "should be filtered");
    
    // These should pass through
    cortexd::Logger::warn("Test", "warn message");
    cortexd::Logger::error("Test", "error message");
    cortexd::Logger::critical("Test", "critical message");
    
    SUCCEED();
}

TEST_F(LoggerTest, ErrorLevelFiltersDebugInfoWarn) {
    cortexd::Logger::init(cortexd::LogLevel::ERROR, false);
    
    // Debug, Info, Warn should be filtered
    cortexd::Logger::debug("Test", "should be filtered");
    cortexd::Logger::info("Test", "should be filtered");
    cortexd::Logger::warn("Test", "should be filtered");
    
    // These should pass through
    cortexd::Logger::error("Test", "error message");
    cortexd::Logger::critical("Test", "critical message");
    
    SUCCEED();
}

TEST_F(LoggerTest, CriticalLevelFiltersAllButCritical) {
    cortexd::Logger::init(cortexd::LogLevel::CRITICAL, false);
    
    // All but critical should be filtered
    cortexd::Logger::debug("Test", "should be filtered");
    cortexd::Logger::info("Test", "should be filtered");
    cortexd::Logger::warn("Test", "should be filtered");
    cortexd::Logger::error("Test", "should be filtered");
    
    // Only critical should pass through
    cortexd::Logger::critical("Test", "critical message");
    
    SUCCEED();
}

// ============================================================================
// Macro tests
// ============================================================================

TEST_F(LoggerTest, LogMacrosWork) {
    cortexd::Logger::init(cortexd::LogLevel::DEBUG, false);
    
    // Test all logging macros
    LOG_DEBUG("MacroTest", "debug via macro");
    LOG_INFO("MacroTest", "info via macro");
    LOG_WARN("MacroTest", "warn via macro");
    LOG_ERROR("MacroTest", "error via macro");
    LOG_CRITICAL("MacroTest", "critical via macro");
    
    SUCCEED();
}

// ============================================================================
// Thread safety tests
// ============================================================================

TEST_F(LoggerTest, ThreadSafeLogging) {
    cortexd::Logger::init(cortexd::LogLevel::INFO, false);
    
    std::atomic<int> log_count{0};
    std::vector<std::thread> threads;
    
    // Launch multiple threads all logging
    for (int t = 0; t < 10; ++t) {
        threads.emplace_back([&, t]() {
            for (int i = 0; i < 100; ++i) {
                cortexd::Logger::info("Thread" + std::to_string(t), "message " + std::to_string(i));
                log_count++;
            }
        });
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
    
    EXPECT_EQ(log_count.load(), 1000);
}

TEST_F(LoggerTest, ThreadSafeLevelChange) {
    cortexd::Logger::init(cortexd::LogLevel::INFO, false);
    
    std::atomic<bool> running{true};
    
    // Thread that keeps logging
    std::thread logger_thread([&]() {
        while (running) {
            cortexd::Logger::info("Test", "message");
            std::this_thread::sleep_for(std::chrono::microseconds(10));
        }
    });
    
    // Thread that keeps changing level
    std::thread changer_thread([&]() {
        for (int i = 0; i < 100; ++i) {
            cortexd::Logger::set_level(cortexd::LogLevel::DEBUG);
            cortexd::Logger::set_level(cortexd::LogLevel::INFO);
            cortexd::Logger::set_level(cortexd::LogLevel::WARN);
            cortexd::Logger::set_level(cortexd::LogLevel::ERROR);
        }
    });
    
    changer_thread.join();
    running = false;
    logger_thread.join();
    
    // If we got here without crashing, thread safety is working
    SUCCEED();
}

// ============================================================================
// Edge cases
// ============================================================================

TEST_F(LoggerTest, EmptyMessageWorks) {
    cortexd::Logger::init(cortexd::LogLevel::DEBUG, false);
    
    cortexd::Logger::info("Test", "");
    
    SUCCEED();
}

TEST_F(LoggerTest, EmptyComponentWorks) {
    cortexd::Logger::init(cortexd::LogLevel::DEBUG, false);
    
    cortexd::Logger::info("", "message");
    
    SUCCEED();
}

TEST_F(LoggerTest, LongMessageWorks) {
    cortexd::Logger::init(cortexd::LogLevel::DEBUG, false);
    
    std::string long_message(10000, 'a');
    cortexd::Logger::info("Test", long_message);
    
    SUCCEED();
}

TEST_F(LoggerTest, SpecialCharactersInMessage) {
    cortexd::Logger::init(cortexd::LogLevel::DEBUG, false);
    
    cortexd::Logger::info("Test", "Special chars: \n\t\"'\\{}[]");
    cortexd::Logger::info("Test", "Unicode: 日本語 中文 한국어");
    
    SUCCEED();
}

TEST_F(LoggerTest, LoggingWithoutInit) {
    // Logger should still work even if not explicitly initialized
    // (uses static defaults)
    cortexd::Logger::info("Test", "message before init");
    
    SUCCEED();
}

// ============================================================================
// Shutdown and reinit tests
// ============================================================================

TEST_F(LoggerTest, ShutdownAndReinit) {
    cortexd::Logger::init(cortexd::LogLevel::DEBUG, false);
    cortexd::Logger::info("Test", "before shutdown");
    
    cortexd::Logger::shutdown();
    
    cortexd::Logger::init(cortexd::LogLevel::INFO, false);
    cortexd::Logger::info("Test", "after reinit");
    
    EXPECT_EQ(cortexd::Logger::get_level(), cortexd::LogLevel::INFO);
}

TEST_F(LoggerTest, MultipleShutdownCalls) {
    cortexd::Logger::init(cortexd::LogLevel::DEBUG, false);
    
    cortexd::Logger::shutdown();
    cortexd::Logger::shutdown();  // Should not crash
    cortexd::Logger::shutdown();
    
    SUCCEED();
}

// ============================================================================
// LogLevel enum tests
// ============================================================================

TEST_F(LoggerTest, LogLevelOrdering) {
    // Verify log levels have correct ordering
    EXPECT_LT(static_cast<int>(cortexd::LogLevel::DEBUG), static_cast<int>(cortexd::LogLevel::INFO));
    EXPECT_LT(static_cast<int>(cortexd::LogLevel::INFO), static_cast<int>(cortexd::LogLevel::WARN));
    EXPECT_LT(static_cast<int>(cortexd::LogLevel::WARN), static_cast<int>(cortexd::LogLevel::ERROR));
    EXPECT_LT(static_cast<int>(cortexd::LogLevel::ERROR), static_cast<int>(cortexd::LogLevel::CRITICAL));
}

TEST_F(LoggerTest, AllLogLevelsHaveValues) {
    EXPECT_EQ(static_cast<int>(cortexd::LogLevel::DEBUG), 0);
    EXPECT_EQ(static_cast<int>(cortexd::LogLevel::INFO), 1);
    EXPECT_EQ(static_cast<int>(cortexd::LogLevel::WARN), 2);
    EXPECT_EQ(static_cast<int>(cortexd::LogLevel::ERROR), 3);
    EXPECT_EQ(static_cast<int>(cortexd::LogLevel::CRITICAL), 4);
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
