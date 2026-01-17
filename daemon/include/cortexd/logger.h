/**
 * @file logger.h
 * @brief Logging utilities for cortexd with journald support
 */

#pragma once

#include <string>
#include <mutex>

namespace cortexd {

// Syslog priority constants (from syslog.h)
namespace internal {
    constexpr int SYSLOG_DEBUG = 7;
    constexpr int SYSLOG_INFO = 6;
    constexpr int SYSLOG_WARNING = 4;
    constexpr int SYSLOG_ERR = 3;
    constexpr int SYSLOG_CRIT = 2;
}

// Logging levels
enum class LogLevel {
    DEBUG = 0,
    INFO = 1,
    WARN = 2,
    ERROR = 3,
    CRITICAL = 4
};

/**
 * @brief Logging utilities with journald and stderr support
 */
class Logger {
public:
    /**
     * @brief Initialize the logger
     * @param min_level Minimum log level to output
     * @param use_journald If true, log to systemd journal; otherwise stderr
     */
    static void init(LogLevel min_level = LogLevel::INFO, bool use_journald = true);
    
    /**
     * @brief Shutdown the logger
     */
    static void shutdown();

    /**
     * @brief Log a debug message
     */
    static void debug(const std::string& component, const std::string& message);
    
    /**
     * @brief Log an info message
     */
    static void info(const std::string& component, const std::string& message);
    
    /**
     * @brief Log a warning message
     */
    static void warn(const std::string& component, const std::string& message);
    
    /**
     * @brief Log an error message
     */
    static void error(const std::string& component, const std::string& message);
    
    /**
     * @brief Log a critical message
     */
    static void critical(const std::string& component, const std::string& message);

    /**
     * @brief Set the minimum log level
     */
    static void set_level(LogLevel level);
    
    /**
     * @brief Get the current log level
     */
    static LogLevel get_level();

private:
    static LogLevel min_level_;
    static bool use_journald_;
    static std::mutex mutex_;
    static bool initialized_;

    /**
     * @brief Log a message at specified level
     */
    static void log(LogLevel level, const std::string& component, const std::string& message);
    
    /**
     * @brief Log to systemd journal
     */
    static void log_to_journald(LogLevel level, const std::string& component, const std::string& message);
    
    /**
     * @brief Log to stderr
     */
    static void log_to_stderr(LogLevel level, const std::string& component, const std::string& message);

    /**
     * @brief Convert log level to syslog priority
     */
    static int level_to_priority(LogLevel level);
    
    /**
     * @brief Convert log level to string
     */
    static const char* level_to_string(LogLevel level);
};

// Convenience macros for logging
#define LOG_DEBUG(component, message) cortexd::Logger::debug(component, message)
#define LOG_INFO(component, message) cortexd::Logger::info(component, message)
#define LOG_WARN(component, message) cortexd::Logger::warn(component, message)
#define LOG_ERROR(component, message) cortexd::Logger::error(component, message)
#define LOG_CRITICAL(component, message) cortexd::Logger::critical(component, message)

} // namespace cortexd