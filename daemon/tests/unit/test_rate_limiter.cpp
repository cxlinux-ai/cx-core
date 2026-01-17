/**
 * @file test_rate_limiter.cpp
 * @brief Unit tests for RateLimiter
 */

#include <gtest/gtest.h>
#include <thread>
#include <chrono>
#include <vector>
#include <atomic>
#include "cortexd/ipc/server.h"
#include "cortexd/logger.h"

class RateLimiterTest : public ::testing::Test {
protected:
    void SetUp() override {
        cortexd::Logger::init(cortexd::LogLevel::ERROR, false);
    }
    
    void TearDown() override {
        cortexd::Logger::shutdown();
    }
};

// ============================================================================
// Basic functionality tests
// ============================================================================

TEST_F(RateLimiterTest, AllowsRequestsUnderLimit) {
    cortexd::RateLimiter limiter(10);  // 10 requests per second
    
    // Should allow 10 requests
    for (int i = 0; i < 10; ++i) {
        EXPECT_TRUE(limiter.allow()) << "Request " << i << " should be allowed";
    }
}

TEST_F(RateLimiterTest, DeniesRequestsOverLimit) {
    cortexd::RateLimiter limiter(5);  // 5 requests per second
    
    // Allow 5 requests
    for (int i = 0; i < 5; ++i) {
        EXPECT_TRUE(limiter.allow());
    }
    
    // 6th request should be denied
    EXPECT_FALSE(limiter.allow());
}

TEST_F(RateLimiterTest, ResetsAfterOneSecond) {
    cortexd::RateLimiter limiter(5);
    
    // Use up the limit
    for (int i = 0; i < 5; ++i) {
        limiter.allow();
    }
    EXPECT_FALSE(limiter.allow());
    
    // Wait for window to reset
    std::this_thread::sleep_for(std::chrono::milliseconds(1100));
    
    // Should allow requests again
    EXPECT_TRUE(limiter.allow());
}

TEST_F(RateLimiterTest, ResetMethodWorks) {
    cortexd::RateLimiter limiter(3);
    
    // Use up the limit
    for (int i = 0; i < 3; ++i) {
        limiter.allow();
    }
    EXPECT_FALSE(limiter.allow());
    
    // Reset
    limiter.reset();
    
    // Should allow requests again
    EXPECT_TRUE(limiter.allow());
}

// ============================================================================
// Edge cases
// ============================================================================

TEST_F(RateLimiterTest, HandlesHighLimit) {
    cortexd::RateLimiter limiter(1000);
    
    // Should allow many requests
    for (int i = 0; i < 1000; ++i) {
        EXPECT_TRUE(limiter.allow());
    }
    
    // 1001st should be denied
    EXPECT_FALSE(limiter.allow());
}

TEST_F(RateLimiterTest, HandlesLimitOfOne) {
    cortexd::RateLimiter limiter(1);
    
    EXPECT_TRUE(limiter.allow());
    EXPECT_FALSE(limiter.allow());
    EXPECT_FALSE(limiter.allow());
}

// ============================================================================
// Thread safety tests
// ============================================================================

TEST_F(RateLimiterTest, ThreadSafetyUnderConcurrentAccess) {
    cortexd::RateLimiter limiter(100);
    std::atomic<int> allowed_count{0};
    std::atomic<int> denied_count{0};
    
    // Launch multiple threads making requests
    std::vector<std::thread> threads;
    for (int t = 0; t < 10; ++t) {
        threads.emplace_back([&]() {
            for (int i = 0; i < 20; ++i) {
                if (limiter.allow()) {
                    allowed_count++;
                } else {
                    denied_count++;
                }
            }
        });
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
    
    // Total requests: 10 threads * 20 requests = 200
    EXPECT_EQ(allowed_count + denied_count, 200);
    
    // Allowed should not exceed limit
    EXPECT_LE(allowed_count.load(), 100);
}

TEST_F(RateLimiterTest, ConcurrentResetIsSafe) {
    cortexd::RateLimiter limiter(50);
    std::atomic<bool> running{true};
    
    // Thread that keeps making requests
    std::thread requester([&]() {
        while (running) {
            limiter.allow();
        }
    });
    
    // Thread that keeps resetting
    std::thread resetter([&]() {
        for (int i = 0; i < 100; ++i) {
            limiter.reset();
            std::this_thread::sleep_for(std::chrono::microseconds(100));
        }
    });
    
    resetter.join();
    running = false;
    requester.join();
    
    // If we got here without crashing, thread safety is working
    SUCCEED();
}

// ============================================================================
// Window behavior tests
// ============================================================================

TEST_F(RateLimiterTest, WindowResetsCorrectly) {
    cortexd::RateLimiter limiter(5);
    
    // Make 3 requests
    for (int i = 0; i < 3; ++i) {
        EXPECT_TRUE(limiter.allow());
    }
    
    // Wait half a second (window hasn't reset)
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    
    // Should still have only 2 remaining
    EXPECT_TRUE(limiter.allow());
    EXPECT_TRUE(limiter.allow());
    EXPECT_FALSE(limiter.allow());
    
    // Wait for full window reset
    std::this_thread::sleep_for(std::chrono::milliseconds(600));
    
    // Should have full capacity again
    EXPECT_TRUE(limiter.allow());
}

TEST_F(RateLimiterTest, MultipleWindowCycles) {
    cortexd::RateLimiter limiter(3);
    
    for (int cycle = 0; cycle < 3; ++cycle) {
        // Use up the limit
        for (int i = 0; i < 3; ++i) {
            EXPECT_TRUE(limiter.allow()) << "Cycle " << cycle << ", request " << i;
        }
        EXPECT_FALSE(limiter.allow()) << "Cycle " << cycle << " should be exhausted";
        
        // Wait for reset
        std::this_thread::sleep_for(std::chrono::milliseconds(1100));
    }
}

// ============================================================================
// Edge case: Window boundary tests
// ============================================================================

TEST_F(RateLimiterTest, WindowBoundaryReset) {
    cortexd::RateLimiter limiter(5);
    
    // Use up the limit
    for (int i = 0; i < 5; ++i) {
        EXPECT_TRUE(limiter.allow());
    }
    EXPECT_FALSE(limiter.allow());
    
    // Wait exactly 1 second (window should reset)
    std::this_thread::sleep_for(std::chrono::milliseconds(1000));
    
    // Should allow requests again immediately after window reset
    EXPECT_TRUE(limiter.allow());
}

TEST_F(RateLimiterTest, RequestsSpanningWindowReset) {
    cortexd::RateLimiter limiter(3);
    
    // Make 2 requests
    EXPECT_TRUE(limiter.allow());
    EXPECT_TRUE(limiter.allow());
    
    // Wait 600ms (halfway through window)
    std::this_thread::sleep_for(std::chrono::milliseconds(600));
    
    // Should still have 1 remaining
    EXPECT_TRUE(limiter.allow());
    EXPECT_FALSE(limiter.allow());
    
    // Wait another 500ms to cross the 1-second boundary
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    
    // Window should have reset, should allow 3 more requests
    EXPECT_TRUE(limiter.allow());
    EXPECT_TRUE(limiter.allow());
    EXPECT_TRUE(limiter.allow());
    EXPECT_FALSE(limiter.allow());
}

int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
