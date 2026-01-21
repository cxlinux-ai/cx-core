/**
 * @file alert_manager.h
 * @brief Alert management with SQLite persistence
 */

#pragma once

#include <string>
#include <vector>
#include <memory>
#include <optional>
#include <chrono>
#include <atomic>
#include <mutex>
#include "cortexd/common.h"

namespace cortexd {

/**
 * @brief Alert severity levels
 */
enum class AlertSeverity {
    INFO = 0,
    WARNING = 1,
    ERROR = 2,
    CRITICAL = 3
};

/**
 * @brief Alert status
 */
enum class AlertStatus {
    ACTIVE = 0,
    ACKNOWLEDGED = 1,
    DISMISSED = 2
};

/**
 * @brief Alert category
 */
enum class AlertCategory {
    CPU = 0,
    MEMORY = 1,
    DISK = 2,
    APT = 3,
    CVE = 4,
    SERVICE = 5,
    SYSTEM = 6
};

/**
 * @brief Alert structure
 */
struct Alert {
    std::string uuid;
    AlertSeverity severity;
    AlertCategory category;
    std::string source;
    std::string message;
    std::string description;
    std::chrono::system_clock::time_point timestamp;
    AlertStatus status;
    std::optional<std::chrono::system_clock::time_point> acknowledged_at;
    std::optional<std::chrono::system_clock::time_point> dismissed_at;
    
    /**
     * @brief Convert alert to JSON
     */
    json to_json() const;
    
    /**
     * @brief Create alert from JSON
     */
    static Alert from_json(const json& j);
};

/**
 * @brief Alert filter for queries
 */
struct AlertFilter {
    std::optional<AlertSeverity> severity;
    std::optional<AlertCategory> category;
    std::optional<AlertStatus> status;
    std::optional<std::string> source;
    bool include_dismissed = false;
};

/**
 * @brief Alert manager with SQLite persistence
 */
class AlertManager {
public:
    /**
     * @brief Construct alert manager
     * @param db_path Path to SQLite database
     */
    explicit AlertManager(const std::string& db_path = "/var/lib/cortex/alerts.db");
    
    ~AlertManager();
    
    /**
     * @brief Initialize database schema
     */
    bool initialize();
    
    /**
     * @brief Create a new alert
     * @param alert Alert to create (UUID will be generated if empty)
     * @return Created alert with UUID
     */
    std::optional<Alert> create_alert(const Alert& alert);
    
    /**
     * @brief Get alert by UUID
     */
    std::optional<Alert> get_alert(const std::string& uuid);
    
    /**
     * @brief Get all alerts matching filter
     */
    std::vector<Alert> get_alerts(const AlertFilter& filter = AlertFilter());
    
    /**
     * @brief Acknowledge an alert
     */
    bool acknowledge_alert(const std::string& uuid);
    
    /**
     * @brief Acknowledge all active alerts
     * @return Number of alerts acknowledged
     */
    size_t acknowledge_all();
    
    /**
     * @brief Dismiss an alert
     */
    bool dismiss_alert(const std::string& uuid);
    
    /**
     * @brief Dismiss all active and acknowledged alerts
     * @return Number of alerts dismissed
     */
    size_t dismiss_all();
    
    /**
     * @brief Get alert counts by severity
     */
    json get_alert_counts();
    
    /**
     * @brief Generate UUID for alert
     */
    static std::string generate_uuid();
    
    /**
     * @brief Convert severity to string
     */
    static std::string severity_to_string(AlertSeverity severity);
    
    /**
     * @brief Convert string to severity
     */
    static AlertSeverity string_to_severity(const std::string& str);
    
    /**
     * @brief Convert category to string
     */
    static std::string category_to_string(AlertCategory category);
    
    /**
     * @brief Convert string to category
     */
    static AlertCategory string_to_category(const std::string& str);
    
    /**
     * @brief Convert status to string
     */
    static std::string status_to_string(AlertStatus status);
    
    /**
     * @brief Convert string to status
     */
    static AlertStatus string_to_status(const std::string& str);

private:
    std::string db_path_;
    void* db_handle_;  // sqlite3* (opaque pointer to avoid including sqlite3.h in header)
    
    // Prepared statement cache
    // NOTE: SQLite prepared statements are NOT thread-safe - must be protected by mutex
    void* stmt_insert_;      // sqlite3_stmt*
    void* stmt_select_;       // sqlite3_stmt*
    void* stmt_select_all_;  // sqlite3_stmt*
    void* stmt_update_ack_;   // sqlite3_stmt*
    void* stmt_update_ack_all_; // sqlite3_stmt*
    void* stmt_update_dismiss_; // sqlite3_stmt*
    void* stmt_update_dismiss_all_; // sqlite3_stmt*
    void* stmt_count_;        // sqlite3_stmt*
    
    // Mutex to protect prepared statement usage (SQLite statements are NOT thread-safe)
    mutable std::mutex stmt_mutex_;
    
    // In-memory alert counters (updated atomically)
    std::atomic<int> count_info_{0};
    std::atomic<int> count_warning_{0};
    std::atomic<int> count_error_{0};
    std::atomic<int> count_critical_{0};
    std::atomic<int> count_total_{0};
    
    /**
     * @brief Ensure database directory exists
     */
    bool ensure_db_directory();
    
    /**
     * @brief Create database schema
     */
    bool create_schema();
    
    /**
     * @brief Prepare and cache all statements
     */
    bool prepare_statements();
    
    /**
     * @brief Finalize all cached statements
     */
    void finalize_statements();
    
    /**
     * @brief Update in-memory counters based on severity
     */
    void update_counters(AlertSeverity severity, int delta);
    
    /**
     * @brief Load initial counters from database
     */
    void load_initial_counters();
};

} // namespace cortexd
