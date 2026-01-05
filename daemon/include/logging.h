#pragma once

#include <string>
#include <mutex>
#include <systemd/sd-journal.h>

namespace cortex {
namespace daemon {

// Logging levels
enum class LogLevel {
    DEBUG = 0,
    INFO = 1,
    WARN = 2,
    ERROR = 3
};

// Logging utilities
class Logger {
public:
    static void init(bool use_journald = true);
    static void shutdown();

    static void debug(const std::string& component, const std::string& message);
    static void info(const std::string& component, const std::string& message);
    static void warn(const std::string& component, const std::string& message);
    static void error(const std::string& component, const std::string& message);

    static void set_level(LogLevel level);
    static LogLevel get_level();

private:
    static bool use_journald_;
    static LogLevel current_level_;
    static std::mutex log_mutex_;

    static int level_to_priority(LogLevel level);
    static const char* level_to_string(LogLevel level);
};

} // namespace daemon
} // namespace cortex
