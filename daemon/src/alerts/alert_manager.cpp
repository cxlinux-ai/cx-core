/**
 * @file alert_manager.cpp
 * @brief Alert management implementation with SQLite persistence
 */

#include "cortexd/alerts/alert_manager.h"
#include "cortexd/logger.h"
#include <sqlite3.h>
#include <uuid/uuid.h>
#include <filesystem>
#include <sstream>
#include <iomanip>
#include <cstring>
#include <unistd.h>
#include <cstdlib>
#include <ctime>

namespace cortexd {

// Cross-platform UTC time conversion helper
// Converts struct tm (assumed to be in UTC) to time_t
static time_t utc_timegm(struct tm* tm) {
#ifdef _WIN32
    return _mkgmtime(tm);
#else
    return timegm(tm);
#endif
}

// Thread-safe UTC time formatting helper
// Formats time_t as ISO 8601 UTC string using gmtime_r
static std::string format_utc_time(time_t time_val) {
    struct tm tm_buf;
#ifdef _WIN32
    // Windows uses _gmtime_s instead of gmtime_r
    if (_gmtime_s(&tm_buf, &time_val) != 0) {
        return "";
    }
#else
    if (gmtime_r(&time_val, &tm_buf) == nullptr) {
        return "";
    }
#endif
    std::stringstream ss;
    ss << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%SZ");
    return ss.str();
}

// Alert JSON conversion
json Alert::to_json() const {
    json j;
    j["uuid"] = uuid;
    j["severity"] = static_cast<int>(severity);
    j["severity_name"] = AlertManager::severity_to_string(severity);
    j["category"] = static_cast<int>(category);
    j["category_name"] = AlertManager::category_to_string(category);
    j["source"] = source;
    j["message"] = message;
    j["description"] = description;
    
    // Convert timestamps to ISO 8601 strings (thread-safe)
    auto time_t = std::chrono::system_clock::to_time_t(timestamp);
    j["timestamp"] = format_utc_time(time_t);
    
    j["status"] = static_cast<int>(status);
    j["status_name"] = AlertManager::status_to_string(status);
    
    if (acknowledged_at.has_value()) {
        auto ack_time_t = std::chrono::system_clock::to_time_t(acknowledged_at.value());
        j["acknowledged_at"] = format_utc_time(ack_time_t);
    }
    
    if (dismissed_at.has_value()) {
        auto dis_time_t = std::chrono::system_clock::to_time_t(dismissed_at.value());
        j["dismissed_at"] = format_utc_time(dis_time_t);
    }
    
    return j;
}

Alert Alert::from_json(const json& j) {
    Alert alert;
    alert.uuid = j.value("uuid", "");
    alert.severity = static_cast<AlertSeverity>(j.value("severity", 0));
    alert.category = static_cast<AlertCategory>(j.value("category", 0));
    alert.source = j.value("source", "");
    alert.message = j.value("message", "");
    alert.description = j.value("description", "");
    
    // Parse timestamp
    std::string timestamp_str = j.value("timestamp", "");
    if (!timestamp_str.empty()) {
        std::tm tm = {};
        std::istringstream ss(timestamp_str);
        ss >> std::get_time(&tm, "%Y-%m-%dT%H:%M:%SZ");
        if (!ss.fail()) {
            alert.timestamp = std::chrono::system_clock::from_time_t(utc_timegm(&tm));
        } else {
            alert.timestamp = std::chrono::system_clock::now();
        }
    } else {
        alert.timestamp = std::chrono::system_clock::now();
    }
    
    alert.status = static_cast<AlertStatus>(j.value("status", 0));
    
    // Parse optional timestamps
    if (j.contains("acknowledged_at") && !j["acknowledged_at"].is_null()) {
        std::string ack_str = j["acknowledged_at"];
        std::tm ack_tm = {};
        std::istringstream ack_ss(ack_str);
        ack_ss >> std::get_time(&ack_tm, "%Y-%m-%dT%H:%M:%SZ");
        if (!ack_ss.fail()) {
            alert.acknowledged_at = std::chrono::system_clock::from_time_t(utc_timegm(&ack_tm));
        }
    }
    
    if (j.contains("dismissed_at") && !j["dismissed_at"].is_null()) {
        std::string dis_str = j["dismissed_at"];
        std::tm dis_tm = {};
        std::istringstream dis_ss(dis_str);
        dis_ss >> std::get_time(&dis_tm, "%Y-%m-%dT%H:%M:%SZ");
        if (!dis_ss.fail()) {
            alert.dismissed_at = std::chrono::system_clock::from_time_t(utc_timegm(&dis_tm));
        }
    }
    
    return alert;
}

// AlertManager implementation
AlertManager::AlertManager(const std::string& db_path)
    : db_path_(db_path), db_handle_(nullptr),
      stmt_insert_(nullptr), stmt_select_(nullptr), stmt_select_all_(nullptr),
      stmt_update_ack_(nullptr), stmt_update_ack_all_(nullptr),
      stmt_update_dismiss_(nullptr), stmt_count_(nullptr) {
}

AlertManager::~AlertManager() {
    finalize_statements();
    if (db_handle_) {
        sqlite3_close(static_cast<sqlite3*>(db_handle_));
    }
}

bool AlertManager::ensure_db_directory() {
    std::filesystem::path db_file(db_path_);
    std::filesystem::path db_dir = db_file.parent_path();
    
    try {
        std::filesystem::create_directories(db_dir);
        
        // Check write permission
        if (!std::filesystem::exists(db_dir) || 
            access(db_dir.c_str(), W_OK) != 0) {
            // Fallback to user directory
            const char* home = getenv("HOME");
            if (home) {
                std::filesystem::path home_dir = std::filesystem::path(home);
                db_dir = home_dir / ".cortex";
                std::filesystem::create_directories(db_dir);
                db_path_ = (db_dir / "alerts.db").string();
                LOG_WARN("AlertManager", "Using user directory for alerts database: " + db_path_);
            } else {
                LOG_ERROR("AlertManager", "Cannot determine home directory for fallback");
                return false;
            }
        }
        
        return true;
    } catch (const std::filesystem::filesystem_error& e) {
        // Check if this is a permission-related error
        if (e.code() == std::errc::permission_denied || 
            e.code() == std::errc::operation_not_permitted) {
            // Fallback to user directory
            const char* home = getenv("HOME");
            if (home) {
                std::filesystem::path home_dir = std::filesystem::path(home);
                db_dir = home_dir / ".cortex";
                try {
                    std::filesystem::create_directories(db_dir);
                    db_path_ = (db_dir / "alerts.db").string();
                    LOG_WARN("AlertManager", "Permission denied for database directory, using user directory: " + db_path_);
                    return true;
                } catch (const std::exception& fallback_e) {
                    LOG_ERROR("AlertManager", "Failed to create fallback database directory: " + std::string(fallback_e.what()) + " (original error: " + std::string(e.what()) + ")");
                    return false;
                }
            } else {
                LOG_ERROR("AlertManager", "Cannot determine home directory for fallback (original error: " + std::string(e.what()) + ")");
                return false;
            }
        } else {
            LOG_ERROR("AlertManager", "Failed to create database directory: " + std::string(e.what()));
            return false;
        }
    } catch (const std::exception& e) {
        LOG_ERROR("AlertManager", "Failed to create database directory: " + std::string(e.what()));
        return false;
    }
}

bool AlertManager::create_schema() {
    sqlite3* db = static_cast<sqlite3*>(db_handle_);
    
    const char* schema_sql = R"(
        CREATE TABLE IF NOT EXISTS alerts (
            uuid TEXT PRIMARY KEY,
            severity INTEGER NOT NULL,
            category INTEGER NOT NULL,
            source TEXT NOT NULL,
            message TEXT NOT NULL,
            description TEXT,
            timestamp TEXT NOT NULL,
            status INTEGER NOT NULL DEFAULT 0,
            acknowledged_at TEXT,
            dismissed_at TEXT
        );
        
        CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
        CREATE INDEX IF NOT EXISTS idx_alerts_category ON alerts(category);
        CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
    )";
    
    char* err_msg = nullptr;
    int rc = sqlite3_exec(db, schema_sql, nullptr, nullptr, &err_msg);
    
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertManager", "Failed to create schema: " + std::string(err_msg ? err_msg : "unknown error"));
        sqlite3_free(err_msg);
        return false;
    }
    
    return true;
}

bool AlertManager::initialize() {
    if (!ensure_db_directory()) {
        return false;
    }
    
    sqlite3* db = nullptr;
    int rc = sqlite3_open(db_path_.c_str(), &db);
    
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertManager", "Failed to open database: " + std::string(sqlite3_errmsg(db)));
        if (db) {
            sqlite3_close(db);
        }
        return false;
    }
    
    db_handle_ = db;
    
    // Enable WAL mode for better concurrency
    sqlite3_exec(db, "PRAGMA journal_mode=WAL", nullptr, nullptr, nullptr);
    sqlite3_exec(db, "PRAGMA synchronous=NORMAL", nullptr, nullptr, nullptr);
    
    if (!create_schema()) {
        sqlite3_close(db);
        db_handle_ = nullptr;
        return false;
    }
    
    // Prepare and cache all statements
    if (!prepare_statements()) {
        sqlite3_close(db);
        db_handle_ = nullptr;
        return false;
    }
    
    // Load initial counters from database
    load_initial_counters();
    
    LOG_INFO("AlertManager", "Initialized alerts database at " + db_path_);
    return true;
}

bool AlertManager::prepare_statements() {
    sqlite3* db = static_cast<sqlite3*>(db_handle_);
    
    const char* insert_sql = R"(
        INSERT INTO alerts (uuid, severity, category, source, message, description, timestamp, status, acknowledged_at, dismissed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    )";
    
    const char* select_sql = "SELECT uuid, severity, category, source, message, description, timestamp, status, acknowledged_at, dismissed_at FROM alerts WHERE uuid = ?";
    
    const char* select_all_sql = "SELECT uuid, severity, category, source, message, description, timestamp, status, acknowledged_at, dismissed_at FROM alerts WHERE 1=1";
    
    const char* update_ack_sql = "UPDATE alerts SET status = ?, acknowledged_at = ? WHERE uuid = ? AND status = ?";
    
    const char* update_ack_all_sql = "UPDATE alerts SET status = ?, acknowledged_at = ? WHERE status = ?";
    
    const char* update_dismiss_sql = "UPDATE alerts SET status = ?, dismissed_at = ? WHERE uuid = ? AND status = ?";
    
    const char* count_sql = "SELECT severity, COUNT(*) FROM alerts WHERE status != ? GROUP BY severity";
    
    int rc;
    
    rc = sqlite3_prepare_v2(db, insert_sql, -1, reinterpret_cast<sqlite3_stmt**>(&stmt_insert_), nullptr);
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertManager", "Failed to prepare insert statement: " + std::string(sqlite3_errmsg(db)));
        return false;
    }
    
    rc = sqlite3_prepare_v2(db, select_sql, -1, reinterpret_cast<sqlite3_stmt**>(&stmt_select_), nullptr);
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertManager", "Failed to prepare select statement: " + std::string(sqlite3_errmsg(db)));
        return false;
    }
    
    rc = sqlite3_prepare_v2(db, select_all_sql, -1, reinterpret_cast<sqlite3_stmt**>(&stmt_select_all_), nullptr);
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertManager", "Failed to prepare select_all statement: " + std::string(sqlite3_errmsg(db)));
        return false;
    }
    
    rc = sqlite3_prepare_v2(db, update_ack_sql, -1, reinterpret_cast<sqlite3_stmt**>(&stmt_update_ack_), nullptr);
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertManager", "Failed to prepare update_ack statement: " + std::string(sqlite3_errmsg(db)));
        return false;
    }
    
    rc = sqlite3_prepare_v2(db, update_ack_all_sql, -1, reinterpret_cast<sqlite3_stmt**>(&stmt_update_ack_all_), nullptr);
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertManager", "Failed to prepare update_ack_all statement: " + std::string(sqlite3_errmsg(db)));
        return false;
    }
    
    rc = sqlite3_prepare_v2(db, update_dismiss_sql, -1, reinterpret_cast<sqlite3_stmt**>(&stmt_update_dismiss_), nullptr);
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertManager", "Failed to prepare update_dismiss statement: " + std::string(sqlite3_errmsg(db)));
        return false;
    }
    
    rc = sqlite3_prepare_v2(db, count_sql, -1, reinterpret_cast<sqlite3_stmt**>(&stmt_count_), nullptr);
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertManager", "Failed to prepare count statement: " + std::string(sqlite3_errmsg(db)));
        return false;
    }
    
    return true;
}

void AlertManager::finalize_statements() {
    if (stmt_insert_) {
        sqlite3_finalize(static_cast<sqlite3_stmt*>(stmt_insert_));
        stmt_insert_ = nullptr;
    }
    if (stmt_select_) {
        sqlite3_finalize(static_cast<sqlite3_stmt*>(stmt_select_));
        stmt_select_ = nullptr;
    }
    if (stmt_select_all_) {
        sqlite3_finalize(static_cast<sqlite3_stmt*>(stmt_select_all_));
        stmt_select_all_ = nullptr;
    }
    if (stmt_update_ack_) {
        sqlite3_finalize(static_cast<sqlite3_stmt*>(stmt_update_ack_));
        stmt_update_ack_ = nullptr;
    }
    if (stmt_update_ack_all_) {
        sqlite3_finalize(static_cast<sqlite3_stmt*>(stmt_update_ack_all_));
        stmt_update_ack_all_ = nullptr;
    }
    if (stmt_update_dismiss_) {
        sqlite3_finalize(static_cast<sqlite3_stmt*>(stmt_update_dismiss_));
        stmt_update_dismiss_ = nullptr;
    }
    if (stmt_count_) {
        sqlite3_finalize(static_cast<sqlite3_stmt*>(stmt_count_));
        stmt_count_ = nullptr;
    }
}

void AlertManager::update_counters(AlertSeverity severity, int delta) {
    switch (severity) {
        case AlertSeverity::INFO:
            count_info_.fetch_add(delta, std::memory_order_relaxed);
            break;
        case AlertSeverity::WARNING:
            count_warning_.fetch_add(delta, std::memory_order_relaxed);
            break;
        case AlertSeverity::ERROR:
            count_error_.fetch_add(delta, std::memory_order_relaxed);
            break;
        case AlertSeverity::CRITICAL:
            count_critical_.fetch_add(delta, std::memory_order_relaxed);
            break;
    }
    count_total_.fetch_add(delta, std::memory_order_relaxed);
}

void AlertManager::load_initial_counters() {
    if (!db_handle_ || !stmt_count_) {
        return;
    }
    
    {
        // SQLite prepared statements are NOT thread-safe - protect with mutex
        std::lock_guard<std::mutex> lock(stmt_mutex_);
        
        sqlite3_stmt* stmt = static_cast<sqlite3_stmt*>(stmt_count_);
        sqlite3_reset(stmt);
        sqlite3_bind_int(stmt, 1, static_cast<int>(AlertStatus::DISMISSED));
        
        count_total_.store(0, std::memory_order_relaxed);
        int total = 0;
        
        int rc;
        while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
            int severity = sqlite3_column_int(stmt, 0);
            int count = sqlite3_column_int(stmt, 1);
            
            switch (static_cast<AlertSeverity>(severity)) {
            case AlertSeverity::INFO:
                count_info_.store(count, std::memory_order_relaxed);
                break;
            case AlertSeverity::WARNING:
                count_warning_.store(count, std::memory_order_relaxed);
                break;
            case AlertSeverity::ERROR:
                count_error_.store(count, std::memory_order_relaxed);
                break;
            case AlertSeverity::CRITICAL:
                count_critical_.store(count, std::memory_order_relaxed);
                break;
            }
            total += count;
        }  // End of while loop
        count_total_.store(total, std::memory_order_relaxed);
    }  // Lock released
}

std::string AlertManager::generate_uuid() {
    uuid_t uuid;
    uuid_generate(uuid);
    char uuid_str[37];
    uuid_unparse(uuid, uuid_str);
    return std::string(uuid_str);
}

std::optional<Alert> AlertManager::create_alert(const Alert& alert) {
    if (!db_handle_) {
        LOG_ERROR("AlertManager", "Database not initialized");
        return std::nullopt;
    }
    
    sqlite3* db = static_cast<sqlite3*>(db_handle_);
    Alert new_alert = alert;
    
    // Generate UUID if not provided
    if (new_alert.uuid.empty()) {
        new_alert.uuid = generate_uuid();
    }
    
    // Set timestamp if not set
    if (new_alert.timestamp.time_since_epoch().count() == 0) {
        new_alert.timestamp = std::chrono::system_clock::now();
    }
    
    // Convert timestamp to ISO 8601 string (thread-safe)
    auto time_t = std::chrono::system_clock::to_time_t(new_alert.timestamp);
    std::string timestamp_str = format_utc_time(time_t);
    
    // Store optional timestamp strings in persistent variables to avoid use-after-free
    std::string ack_ts;
    std::string dis_ts;
    
    if (new_alert.acknowledged_at.has_value()) {
        auto ack_time_t = std::chrono::system_clock::to_time_t(new_alert.acknowledged_at.value());
        ack_ts = format_utc_time(ack_time_t);
    }
    
    if (new_alert.dismissed_at.has_value()) {
        auto dis_time_t = std::chrono::system_clock::to_time_t(new_alert.dismissed_at.value());
        dis_ts = format_utc_time(dis_time_t);
    }
    
    int rc;
    {
        // SQLite prepared statements are NOT thread-safe - protect with mutex
        std::lock_guard<std::mutex> lock(stmt_mutex_);
        
        sqlite3_stmt* stmt = static_cast<sqlite3_stmt*>(stmt_insert_);
        sqlite3_reset(stmt);
        
        sqlite3_bind_text(stmt, 1, new_alert.uuid.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 2, static_cast<int>(new_alert.severity));
        sqlite3_bind_int(stmt, 3, static_cast<int>(new_alert.category));
        sqlite3_bind_text(stmt, 4, new_alert.source.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 5, new_alert.message.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 6, new_alert.description.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 7, timestamp_str.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_int(stmt, 8, static_cast<int>(new_alert.status));
        
        if (new_alert.acknowledged_at.has_value()) {
            sqlite3_bind_text(stmt, 9, ack_ts.c_str(), -1, SQLITE_TRANSIENT);
        } else {
            sqlite3_bind_null(stmt, 9);
        }
        
        if (new_alert.dismissed_at.has_value()) {
            sqlite3_bind_text(stmt, 10, dis_ts.c_str(), -1, SQLITE_TRANSIENT);
        } else {
            sqlite3_bind_null(stmt, 10);
        }
        
        rc = sqlite3_step(stmt);
    }  // Lock released here
    
    if (rc != SQLITE_DONE) {
        LOG_ERROR("AlertManager", "Failed to insert alert: " + std::string(sqlite3_errmsg(db)));
        return std::nullopt;
    }
    
    // Update counters (only for active alerts) - atomics are thread-safe
    if (new_alert.status == AlertStatus::ACTIVE) {
        update_counters(new_alert.severity, 1);
    }
    
    LOG_DEBUG("AlertManager", "Created alert: " + new_alert.uuid);
    return new_alert;
}

std::optional<Alert> AlertManager::get_alert(const std::string& uuid) {
    if (!db_handle_ || !stmt_select_) {
        return std::nullopt;
    }
    
    Alert alert;
    {
        // SQLite prepared statements are NOT thread-safe - protect with mutex
        std::lock_guard<std::mutex> lock(stmt_mutex_);
        
        sqlite3_stmt* stmt = static_cast<sqlite3_stmt*>(stmt_select_);
        sqlite3_reset(stmt);
        sqlite3_bind_text(stmt, 1, uuid.c_str(), -1, SQLITE_STATIC);
        
        int rc = sqlite3_step(stmt);
        if (rc != SQLITE_ROW) {
            return std::nullopt;
        }
        
        // Read all columns while lock is held (stmt is only valid during lock)
        const unsigned char* uuid_txt = sqlite3_column_text(stmt, 0);
        alert.uuid = uuid_txt ? reinterpret_cast<const char*>(uuid_txt) : std::string();
        alert.severity = static_cast<AlertSeverity>(sqlite3_column_int(stmt, 1));
        alert.category = static_cast<AlertCategory>(sqlite3_column_int(stmt, 2));
        const unsigned char* source_txt = sqlite3_column_text(stmt, 3);
        alert.source = source_txt ? reinterpret_cast<const char*>(source_txt) : std::string();
        const unsigned char* message_txt = sqlite3_column_text(stmt, 4);
        alert.message = message_txt ? reinterpret_cast<const char*>(message_txt) : std::string();
        const unsigned char* desc_txt = sqlite3_column_text(stmt, 5);
        alert.description = desc_txt ? reinterpret_cast<const char*>(desc_txt) : std::string();
        
        // Parse timestamp
        const unsigned char* raw = sqlite3_column_text(stmt, 6);
        if (raw != nullptr) {
            std::string timestamp_str = reinterpret_cast<const char*>(raw);
            if (!timestamp_str.empty()) {
                std::tm tm = {};
                std::istringstream ss(timestamp_str);
                ss >> std::get_time(&tm, "%Y-%m-%dT%H:%M:%SZ");
                if (!ss.fail()) {
                    alert.timestamp = std::chrono::system_clock::from_time_t(utc_timegm(&tm));
                } else {
                    alert.timestamp = std::chrono::system_clock::now();
                }
            } else {
                alert.timestamp = std::chrono::system_clock::now();
            }
        } else {
            alert.timestamp = std::chrono::system_clock::now();
        }
        
        alert.status = static_cast<AlertStatus>(sqlite3_column_int(stmt, 7));
        
        // Parse optional timestamps
        if (sqlite3_column_type(stmt, 8) != SQLITE_NULL) {
            std::string ack_str = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 8));
            std::tm ack_tm = {};
            std::istringstream ack_ss(ack_str);
            ack_ss >> std::get_time(&ack_tm, "%Y-%m-%dT%H:%M:%SZ");
            if (!ack_ss.fail()) {
                alert.acknowledged_at = std::chrono::system_clock::from_time_t(utc_timegm(&ack_tm));
            }
        }
        
        if (sqlite3_column_type(stmt, 9) != SQLITE_NULL) {
            std::string dis_str = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 9));
            std::tm dis_tm = {};
            std::istringstream dis_ss(dis_str);
            dis_ss >> std::get_time(&dis_tm, "%Y-%m-%dT%H:%M:%SZ");
            if (!dis_ss.fail()) {
                alert.dismissed_at = std::chrono::system_clock::from_time_t(utc_timegm(&dis_tm));
            }
        }
    }  // Lock released - alert data is now copied
    
    return alert;
}

std::vector<Alert> AlertManager::get_alerts(const AlertFilter& filter) {
    std::vector<Alert> alerts;
    
    if (!db_handle_) {
        return alerts;
    }
    
    sqlite3* db = static_cast<sqlite3*>(db_handle_);
    
    std::string select_sql = "SELECT uuid, severity, category, source, message, description, timestamp, status, acknowledged_at, dismissed_at FROM alerts WHERE 1=1";
    
    if (filter.severity.has_value()) {
        select_sql += " AND severity = " + std::to_string(static_cast<int>(filter.severity.value()));
    }
    
    if (filter.category.has_value()) {
        select_sql += " AND category = " + std::to_string(static_cast<int>(filter.category.value()));
    }
    
    if (filter.status.has_value()) {
        select_sql += " AND status = " + std::to_string(static_cast<int>(filter.status.value()));
    } else if (!filter.include_dismissed) {
        select_sql += " AND status != " + std::to_string(static_cast<int>(AlertStatus::DISMISSED));
    }
    
    int param_index = 1;
    if (filter.source.has_value()) {
        select_sql += " AND source = ?";
    }
    
    select_sql += " ORDER BY timestamp DESC";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(db, select_sql.c_str(), -1, &stmt, nullptr);
    
    if (rc != SQLITE_OK) {
        return alerts;
    }
    
    if (filter.source.has_value()) {
        sqlite3_bind_text(stmt, param_index++, filter.source.value().c_str(), -1, SQLITE_STATIC);
    }
    
    while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
        Alert alert;
        const unsigned char* uuid_txt = sqlite3_column_text(stmt, 0);
        alert.uuid = uuid_txt ? reinterpret_cast<const char*>(uuid_txt) : std::string();
        alert.severity = static_cast<AlertSeverity>(sqlite3_column_int(stmt, 1));
        alert.category = static_cast<AlertCategory>(sqlite3_column_int(stmt, 2));
        const unsigned char* source_txt = sqlite3_column_text(stmt, 3);
        alert.source = source_txt ? reinterpret_cast<const char*>(source_txt) : std::string();
        const unsigned char* message_txt = sqlite3_column_text(stmt, 4);
        alert.message = message_txt ? reinterpret_cast<const char*>(message_txt) : std::string();
        const unsigned char* desc_txt = sqlite3_column_text(stmt, 5);
        alert.description = desc_txt ? reinterpret_cast<const char*>(desc_txt) : std::string();
        
        // Parse timestamp
        const unsigned char* raw = sqlite3_column_text(stmt, 6);
        if (raw != nullptr) {
            std::string timestamp_str = reinterpret_cast<const char*>(raw);
            if (!timestamp_str.empty()) {
                std::tm tm = {};
                std::istringstream ss(timestamp_str);
                ss >> std::get_time(&tm, "%Y-%m-%dT%H:%M:%SZ");
                if (!ss.fail()) {
                    alert.timestamp = std::chrono::system_clock::from_time_t(utc_timegm(&tm));
                } else {
                    alert.timestamp = std::chrono::system_clock::now();
                }
            } else {
                alert.timestamp = std::chrono::system_clock::now();
            }
        } else {
            alert.timestamp = std::chrono::system_clock::now();
        }
        
        alert.status = static_cast<AlertStatus>(sqlite3_column_int(stmt, 7));
        
        // Parse optional timestamps
        if (sqlite3_column_type(stmt, 8) != SQLITE_NULL) {
            std::string ack_str = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 8));
            std::tm ack_tm = {};
            std::istringstream ack_ss(ack_str);
            ack_ss >> std::get_time(&ack_tm, "%Y-%m-%dT%H:%M:%SZ");
            if (!ack_ss.fail()) {
                alert.acknowledged_at = std::chrono::system_clock::from_time_t(utc_timegm(&ack_tm));
            }
        }
        
        if (sqlite3_column_type(stmt, 9) != SQLITE_NULL) {
            std::string dis_str = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 9));
            std::tm dis_tm = {};
            std::istringstream dis_ss(dis_str);
            dis_ss >> std::get_time(&dis_tm, "%Y-%m-%dT%H:%M:%SZ");
            if (!dis_ss.fail()) {
                alert.dismissed_at = std::chrono::system_clock::from_time_t(utc_timegm(&dis_tm));
            }
        }
        
        alerts.push_back(alert);
    }
    
    sqlite3_finalize(stmt);
    return alerts;
}

bool AlertManager::acknowledge_alert(const std::string& uuid) {
    if (!db_handle_ || !stmt_update_ack_) {
        return false;
    }
    
    // Get alert first to know its severity for counter update
    auto alert_opt = get_alert(uuid);
    if (!alert_opt || alert_opt->status != AlertStatus::ACTIVE) {
        return false;
    }
    
    sqlite3* db = static_cast<sqlite3*>(db_handle_);
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::string timestamp_str = format_utc_time(time_t);
    
    int rc;
    int changes = 0;
    {
        // SQLite prepared statements are NOT thread-safe - protect with mutex
        std::lock_guard<std::mutex> lock(stmt_mutex_);
        
        sqlite3_stmt* stmt = static_cast<sqlite3_stmt*>(stmt_update_ack_);
        sqlite3_reset(stmt);
        
        sqlite3_bind_int(stmt, 1, static_cast<int>(AlertStatus::ACKNOWLEDGED));
        sqlite3_bind_text(stmt, 2, timestamp_str.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 3, uuid.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 4, static_cast<int>(AlertStatus::ACTIVE));
        
        rc = sqlite3_step(stmt);
        changes = (rc == SQLITE_DONE) ? sqlite3_changes(db) : 0;
    }  // Lock released
    
    if (rc == SQLITE_DONE && changes > 0) {
        // Update counters (decrement active count) - atomics are thread-safe
        update_counters(alert_opt->severity, -1);
        return true;
    }
    
    return false;
}

size_t AlertManager::acknowledge_all() {
    if (!db_handle_ || !stmt_update_ack_all_) {
        return 0;
    }
    
    sqlite3* db = static_cast<sqlite3*>(db_handle_);
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::string timestamp_str = format_utc_time(time_t);
    
    int rc;
    int changes = 0;
    {
        // SQLite prepared statements are NOT thread-safe - protect with mutex
        std::lock_guard<std::mutex> lock(stmt_mutex_);
        
        sqlite3_stmt* stmt = static_cast<sqlite3_stmt*>(stmt_update_ack_all_);
        sqlite3_reset(stmt);
        
        sqlite3_bind_int(stmt, 1, static_cast<int>(AlertStatus::ACKNOWLEDGED));
        sqlite3_bind_text(stmt, 2, timestamp_str.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 3, static_cast<int>(AlertStatus::ACTIVE));
        
        rc = sqlite3_step(stmt);
        changes = (rc == SQLITE_DONE) ? sqlite3_changes(db) : 0;
        
        // Update counters while holding lock to prevent race with concurrent inserts
        // Reset all to 0 since all active alerts are now acknowledged
        // Note: This is approximate - for exact counts we'd need to query by severity
        // But for acknowledge_all, we typically want to clear all counters anyway
        if (changes > 0) {
            count_info_.store(0, std::memory_order_relaxed);
            count_warning_.store(0, std::memory_order_relaxed);
            count_error_.store(0, std::memory_order_relaxed);
            count_critical_.store(0, std::memory_order_relaxed);
            count_total_.store(0, std::memory_order_relaxed);
        }
    }  // Lock released
    
    return changes;
}

bool AlertManager::dismiss_alert(const std::string& uuid) {
    if (!db_handle_ || !stmt_update_dismiss_) {
        return false;
    }
    
    // Get alert first to know its severity and status for counter update
    auto alert_opt = get_alert(uuid);
    if (!alert_opt) {
        return false;
    }
    
    // Only update counters if alert was active or acknowledged (not already dismissed)
    bool should_update_counters = (alert_opt->status == AlertStatus::ACTIVE || 
                                   alert_opt->status == AlertStatus::ACKNOWLEDGED);
    
    sqlite3* db = static_cast<sqlite3*>(db_handle_);
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    std::string timestamp_str = format_utc_time(time_t);
    
    int rc;
    int changes = 0;
    AlertStatus expected_status = alert_opt->status;
    {
        // SQLite prepared statements are NOT thread-safe - protect with mutex
        std::lock_guard<std::mutex> lock(stmt_mutex_);
        
        sqlite3_stmt* stmt = static_cast<sqlite3_stmt*>(stmt_update_dismiss_);
        sqlite3_reset(stmt);
        
        sqlite3_bind_int(stmt, 1, static_cast<int>(AlertStatus::DISMISSED));
        sqlite3_bind_text(stmt, 2, timestamp_str.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 3, uuid.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 4, static_cast<int>(expected_status));
        
        rc = sqlite3_step(stmt);
        changes = (rc == SQLITE_DONE) ? sqlite3_changes(db) : 0;
    }  // Lock released
    
    if (rc == SQLITE_DONE && changes > 0) {
        // Update counters if alert was active - atomics are thread-safe
        if (should_update_counters && expected_status == AlertStatus::ACTIVE) {
            update_counters(alert_opt->severity, -1);
        }
        return true;
    }
    
    return false;
}

json AlertManager::get_alert_counts() {
    // Use in-memory counters for O(1) performance
    json counts;
    counts["info"] = count_info_.load(std::memory_order_relaxed);
    counts["warning"] = count_warning_.load(std::memory_order_relaxed);
    counts["error"] = count_error_.load(std::memory_order_relaxed);
    counts["critical"] = count_critical_.load(std::memory_order_relaxed);
    counts["total"] = count_total_.load(std::memory_order_relaxed);
    
    return counts;
}

// Static helper methods
std::string AlertManager::severity_to_string(AlertSeverity severity) {
    switch (severity) {
        case AlertSeverity::INFO: return "info";
        case AlertSeverity::WARNING: return "warning";
        case AlertSeverity::ERROR: return "error";
        case AlertSeverity::CRITICAL: return "critical";
        default: return "unknown";
    }
}

AlertSeverity AlertManager::string_to_severity(const std::string& str) {
    if (str == "info") return AlertSeverity::INFO;
    if (str == "warning") return AlertSeverity::WARNING;
    if (str == "error") return AlertSeverity::ERROR;
    if (str == "critical") return AlertSeverity::CRITICAL;
    return AlertSeverity::INFO;
}

std::string AlertManager::category_to_string(AlertCategory category) {
    switch (category) {
        case AlertCategory::CPU: return "cpu";
        case AlertCategory::MEMORY: return "memory";
        case AlertCategory::DISK: return "disk";
        case AlertCategory::APT: return "apt";
        case AlertCategory::CVE: return "cve";
        case AlertCategory::SERVICE: return "service";
        case AlertCategory::SYSTEM: return "system";
        default: return "unknown";
    }
}

AlertCategory AlertManager::string_to_category(const std::string& str) {
    if (str == "cpu") return AlertCategory::CPU;
    if (str == "memory") return AlertCategory::MEMORY;
    if (str == "disk") return AlertCategory::DISK;
    if (str == "apt") return AlertCategory::APT;
    if (str == "cve") return AlertCategory::CVE;
    if (str == "service") return AlertCategory::SERVICE;
    if (str == "system") return AlertCategory::SYSTEM;
    return AlertCategory::SYSTEM;
}

std::string AlertManager::status_to_string(AlertStatus status) {
    switch (status) {
        case AlertStatus::ACTIVE: return "active";
        case AlertStatus::ACKNOWLEDGED: return "acknowledged";
        case AlertStatus::DISMISSED: return "dismissed";
        default: return "unknown";
    }
}

AlertStatus AlertManager::string_to_status(const std::string& str) {
    if (str == "active") return AlertStatus::ACTIVE;
    if (str == "acknowledged") return AlertStatus::ACKNOWLEDGED;
    if (str == "dismissed") return AlertStatus::DISMISSED;
    return AlertStatus::ACTIVE;
}

} // namespace cortexd
