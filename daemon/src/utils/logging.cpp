#include "logging.h"
#include <iostream>
#include <mutex>
#include <ctime>
#include <iomanip>
#include <sstream>

namespace cortex {
namespace daemon {

bool Logger::use_journald_ = true;
LogLevel Logger::current_level_ = LogLevel::INFO;
std::mutex Logger::log_mutex_;

void Logger::init(bool use_journald) {
    std::lock_guard<std::mutex> lock(log_mutex_);
    use_journald_ = use_journald;
    if (!use_journald_) {
        std::cerr << "[cortexd] Logging initialized (stderr mode)" << std::endl;
    }
}

void Logger::shutdown() {
    std::lock_guard<std::mutex> lock(log_mutex_);
    if (!use_journald_) {
        std::cerr << "[cortexd] Logging shutdown" << std::endl;
    }
}

void Logger::debug(const std::string& component, const std::string& message) {
    if (current_level_ <= LogLevel::DEBUG) {
        std::lock_guard<std::mutex> lock(log_mutex_);
        if (use_journald_) {
            sd_journal_send("MESSAGE=%s", message.c_str(),
                          "PRIORITY=%d", LOG_DEBUG,
                          "COMPONENT=%s", component.c_str(),
                          NULL);
        } else {
            std::cerr << "[DEBUG] " << component << ": " << message << std::endl;
        }
    }
}

void Logger::info(const std::string& component, const std::string& message) {
    if (current_level_ <= LogLevel::INFO) {
        std::lock_guard<std::mutex> lock(log_mutex_);
        if (use_journald_) {
            sd_journal_send("MESSAGE=%s", message.c_str(),
                          "PRIORITY=%d", LOG_INFO,
                          "COMPONENT=%s", component.c_str(),
                          NULL);
        } else {
            std::cerr << "[INFO] " << component << ": " << message << std::endl;
        }
    }
}

void Logger::warn(const std::string& component, const std::string& message) {
    if (current_level_ <= LogLevel::WARN) {
        std::lock_guard<std::mutex> lock(log_mutex_);
        if (use_journald_) {
            sd_journal_send("MESSAGE=%s", message.c_str(),
                          "PRIORITY=%d", LOG_WARNING,
                          "COMPONENT=%s", component.c_str(),
                          NULL);
        } else {
            std::cerr << "[WARN] " << component << ": " << message << std::endl;
        }
    }
}

void Logger::error(const std::string& component, const std::string& message) {
    if (current_level_ <= LogLevel::ERROR) {
        std::lock_guard<std::mutex> lock(log_mutex_);
        if (use_journald_) {
            sd_journal_send("MESSAGE=%s", message.c_str(),
                          "PRIORITY=%d", LOG_ERR,
                          "COMPONENT=%s", component.c_str(),
                          NULL);
        } else {
            std::cerr << "[ERROR] " << component << ": " << message << std::endl;
        }
    }
}

void Logger::set_level(LogLevel level) {
    std::lock_guard<std::mutex> lock(log_mutex_);
    current_level_ = level;
}

LogLevel Logger::get_level() {
    std::lock_guard<std::mutex> lock(log_mutex_);
    return current_level_;
}

int Logger::level_to_priority(LogLevel level) {
    switch (level) {
        case LogLevel::DEBUG:
            return LOG_DEBUG;
        case LogLevel::INFO:
            return LOG_INFO;
        case LogLevel::WARN:
            return LOG_WARNING;
        case LogLevel::ERROR:
            return LOG_ERR;
        default:
            return LOG_INFO;
    }
}

const char* Logger::level_to_string(LogLevel level) {
    switch (level) {
        case LogLevel::DEBUG:
            return "DEBUG";
        case LogLevel::INFO:
            return "INFO";
        case LogLevel::WARN:
            return "WARN";
        case LogLevel::ERROR:
            return "ERROR";
        default:
            return "UNKNOWN";
    }
}

} // namespace daemon
} // namespace cortex
