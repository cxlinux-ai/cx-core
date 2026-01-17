/**
 * @file logger.cpp
 * @brief Logger implementation with journald and stderr support
 */

 #include "cortexd/logger.h"
 #include <iostream>
 #include <iomanip>
 #include <ctime>
 #include <systemd/sd-journal.h>
 
 namespace cortexd {
 
 // Static member initialization
 LogLevel Logger::min_level_ = LogLevel::INFO;
 bool Logger::use_journald_ = true;
 std::mutex Logger::mutex_;
 bool Logger::initialized_ = false;
 
 void Logger::init(LogLevel min_level, bool use_journald) {
     std::lock_guard<std::mutex> lock(mutex_);
     min_level_ = min_level;
     use_journald_ = use_journald;
     initialized_ = true;
     
     if (!use_journald_) {
         std::cerr << "[cortexd] Logging initialized (stderr mode, level=" 
                   << level_to_string(min_level_) << ")" << std::endl;
     }
 }
 
 void Logger::shutdown() {
     std::lock_guard<std::mutex> lock(mutex_);
     if (initialized_ && !use_journald_) {
         std::cerr << "[cortexd] Logging shutdown" << std::endl;
     }
     initialized_ = false;
 }
 
 void Logger::set_level(LogLevel level) {
     std::lock_guard<std::mutex> lock(mutex_);
     min_level_ = level;
 }
 
 LogLevel Logger::get_level() {
     std::lock_guard<std::mutex> lock(mutex_);
     return min_level_;
 }
 
 void Logger::debug(const std::string& component, const std::string& message) {
     log(LogLevel::DEBUG, component, message);
 }
 
 void Logger::info(const std::string& component, const std::string& message) {
     log(LogLevel::INFO, component, message);
 }
 
 void Logger::warn(const std::string& component, const std::string& message) {
     log(LogLevel::WARN, component, message);
 }
 
 void Logger::error(const std::string& component, const std::string& message) {
     log(LogLevel::ERROR, component, message);
 }
 
 void Logger::critical(const std::string& component, const std::string& message) {
     log(LogLevel::CRITICAL, component, message);
 }
 
void Logger::log(LogLevel level, const std::string& component, const std::string& message) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    // Check log level while holding the lock to avoid race condition
    if (static_cast<int>(level) < static_cast<int>(min_level_)) {
        return;
    }
    
    if (use_journald_) {
        log_to_journald(level, component, message);
    } else {
        log_to_stderr(level, component, message);
    }
}
 
 void Logger::log_to_journald(LogLevel level, const std::string& component, const std::string& message) {
     sd_journal_send(
         "MESSAGE=%s", message.c_str(),
         "PRIORITY=%d", level_to_priority(level),
         "SYSLOG_IDENTIFIER=cortexd",
         "CORTEXD_COMPONENT=%s", component.c_str(),
         "CODE_FUNC=%s", component.c_str(),
         NULL
     );
 }
 
void Logger::log_to_stderr(LogLevel level, const std::string& component, const std::string& message) {
    // Get current time using thread-safe localtime_r (POSIX)
    auto now = std::time(nullptr);
    std::tm tm_buf{};
    std::tm* tm = localtime_r(&now, &tm_buf);
    
    // Format: [TIMESTAMP] [LEVEL] component: message
    if (tm) {
        std::cerr << std::put_time(tm, "[%Y-%m-%d %H:%M:%S]")
                  << " [" << level_to_string(level) << "]"
                  << " " << component << ": "
                  << message << std::endl;
    } else {
        // Fallback if localtime_r fails
        std::cerr << "[XXXX-XX-XX XX:XX:XX]"
                  << " [" << level_to_string(level) << "]"
                  << " " << component << ": "
                  << message << std::endl;
    }
}
 
 int Logger::level_to_priority(LogLevel level) {
     switch (level) {
         case LogLevel::DEBUG: return internal::SYSLOG_DEBUG;
         case LogLevel::INFO: return internal::SYSLOG_INFO;
         case LogLevel::WARN: return internal::SYSLOG_WARNING;
         case LogLevel::ERROR: return internal::SYSLOG_ERR;
         case LogLevel::CRITICAL: return internal::SYSLOG_CRIT;
         default: return internal::SYSLOG_INFO;
     }
 }
 
 const char* Logger::level_to_string(LogLevel level) {
     switch (level) {
         case LogLevel::DEBUG: return "DEBUG";
         case LogLevel::INFO: return "INFO";
         case LogLevel::WARN: return "WARN";
         case LogLevel::ERROR: return "ERROR";
         case LogLevel::CRITICAL: return "CRITICAL";
         default: return "UNKNOWN";
     }
 }
 
 } // namespace cortexd