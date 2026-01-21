/**
 * @file test_alert_manager.cpp
 * @brief Unit tests for AlertManager
 */

#include <gtest/gtest.h>
#include "cortexd/alerts/alert_manager.h"
#include <filesystem>
#include <fstream>
#include <cstdio>

using namespace cortexd;

class AlertManagerTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Create temporary database path
        test_db_path_ = "/tmp/test_alerts_" + std::to_string(getpid()) + ".db";
        
        // Remove test database if it exists
        if (std::filesystem::exists(test_db_path_)) {
            std::filesystem::remove(test_db_path_);
        }
        
        alert_manager_ = std::make_unique<AlertManager>(test_db_path_);
        ASSERT_TRUE(alert_manager_->initialize());
    }
    
    void TearDown() override {
        alert_manager_.reset();
        
        // Clean up test database
        if (std::filesystem::exists(test_db_path_)) {
            std::filesystem::remove(test_db_path_);
        }
    }
    
    std::string test_db_path_;
    std::unique_ptr<AlertManager> alert_manager_;
};

TEST_F(AlertManagerTest, CreateAlert) {
    Alert alert;
    alert.severity = AlertSeverity::WARNING;
    alert.category = AlertCategory::CPU;
    alert.source = "test_source";
    alert.message = "Test alert message";
    alert.description = "Test alert description";
    alert.status = AlertStatus::ACTIVE;
    alert.timestamp = std::chrono::system_clock::now();
    
    auto created = alert_manager_->create_alert(alert);
    ASSERT_TRUE(created.has_value());
    ASSERT_FALSE(created->uuid.empty());
    ASSERT_EQ(created->message, "Test alert message");
}

TEST_F(AlertManagerTest, GetAlert) {
    Alert alert;
    alert.severity = AlertSeverity::ERROR;
    alert.category = AlertCategory::MEMORY;
    alert.source = "test_source";
    alert.message = "Test alert";
    alert.status = AlertStatus::ACTIVE;
    
    auto created = alert_manager_->create_alert(alert);
    ASSERT_TRUE(created.has_value());
    
    auto retrieved = alert_manager_->get_alert(created->uuid);
    ASSERT_TRUE(retrieved.has_value());
    ASSERT_EQ(retrieved->uuid, created->uuid);
    ASSERT_EQ(retrieved->message, "Test alert");
    ASSERT_EQ(retrieved->severity, AlertSeverity::ERROR);
}

TEST_F(AlertManagerTest, GetAlertsFilterBySeverity) {
    // Create alerts with different severities
    Alert alert1;
    alert1.severity = AlertSeverity::WARNING;
    alert1.category = AlertCategory::CPU;
    alert1.source = "test";
    alert1.message = "Warning alert";
    alert1.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert1);
    
    Alert alert2;
    alert2.severity = AlertSeverity::ERROR;
    alert2.category = AlertCategory::MEMORY;
    alert2.source = "test";
    alert2.message = "Error alert";
    alert2.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert2);
    
    AlertFilter filter;
    filter.severity = AlertSeverity::WARNING;
    auto alerts = alert_manager_->get_alerts(filter);
    
    ASSERT_EQ(alerts.size(), 1);
    ASSERT_EQ(alerts[0].severity, AlertSeverity::WARNING);
}

TEST_F(AlertManagerTest, GetAlertsFilterByCategory) {
    Alert alert1;
    alert1.severity = AlertSeverity::INFO;
    alert1.category = AlertCategory::CPU;
    alert1.source = "test";
    alert1.message = "CPU alert";
    alert1.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert1);
    
    Alert alert2;
    alert2.severity = AlertSeverity::INFO;
    alert2.category = AlertCategory::DISK;
    alert2.source = "test";
    alert2.message = "Disk alert";
    alert2.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert2);
    
    AlertFilter filter;
    filter.category = AlertCategory::CPU;
    auto alerts = alert_manager_->get_alerts(filter);
    
    ASSERT_EQ(alerts.size(), 1);
    ASSERT_EQ(alerts[0].category, AlertCategory::CPU);
}

TEST_F(AlertManagerTest, AcknowledgeAlert) {
    Alert alert;
    alert.severity = AlertSeverity::WARNING;
    alert.category = AlertCategory::CPU;
    alert.source = "test";
    alert.message = "Test alert";
    alert.status = AlertStatus::ACTIVE;
    
    auto created = alert_manager_->create_alert(alert);
    ASSERT_TRUE(created.has_value());
    
    bool acknowledged = alert_manager_->acknowledge_alert(created->uuid);
    ASSERT_TRUE(acknowledged);
    
    auto retrieved = alert_manager_->get_alert(created->uuid);
    ASSERT_TRUE(retrieved.has_value());
    ASSERT_EQ(retrieved->status, AlertStatus::ACKNOWLEDGED);
    ASSERT_TRUE(retrieved->acknowledged_at.has_value());
}

TEST_F(AlertManagerTest, AcknowledgeAll) {
    // Create multiple active alerts
    for (int i = 0; i < 3; ++i) {
        Alert alert;
        alert.severity = AlertSeverity::WARNING;
        alert.category = AlertCategory::CPU;
        alert.source = "test";
        alert.message = "Alert " + std::to_string(i);
        alert.status = AlertStatus::ACTIVE;
        alert_manager_->create_alert(alert);
    }
    
    size_t count = alert_manager_->acknowledge_all();
    ASSERT_EQ(count, 3);
    
    AlertFilter filter;
    filter.status = AlertStatus::ACKNOWLEDGED;
    auto alerts = alert_manager_->get_alerts(filter);
    ASSERT_EQ(alerts.size(), 3);
}

TEST_F(AlertManagerTest, DismissAlert) {
    Alert alert;
    alert.severity = AlertSeverity::WARNING;
    alert.category = AlertCategory::CPU;
    alert.source = "test";
    alert.message = "Test alert";
    alert.status = AlertStatus::ACTIVE;
    
    auto created = alert_manager_->create_alert(alert);
    ASSERT_TRUE(created.has_value());
    
    bool dismissed = alert_manager_->dismiss_alert(created->uuid);
    ASSERT_TRUE(dismissed);
    
    auto retrieved = alert_manager_->get_alert(created->uuid);
    ASSERT_TRUE(retrieved.has_value());
    ASSERT_EQ(retrieved->status, AlertStatus::DISMISSED);
    ASSERT_TRUE(retrieved->dismissed_at.has_value());
}

TEST_F(AlertManagerTest, DismissAll) {
    // Create multiple active and acknowledged alerts
    for (int i = 0; i < 3; ++i) {
        Alert alert;
        alert.severity = AlertSeverity::WARNING;
        alert.category = AlertCategory::CPU;
        alert.source = "test";
        alert.message = "Alert " + std::to_string(i);
        alert.status = AlertStatus::ACTIVE;
        alert_manager_->create_alert(alert);
    }
    
    // Acknowledge one alert
    AlertFilter filter;
    filter.status = AlertStatus::ACTIVE;
    auto active_alerts = alert_manager_->get_alerts(filter);
    if (!active_alerts.empty()) {
        alert_manager_->acknowledge_alert(active_alerts[0].uuid);
    }
    
    size_t count = alert_manager_->dismiss_all();
    ASSERT_GE(count, 3);  // Should dismiss all active and acknowledged alerts
    
    AlertFilter dismissed_filter;
    dismissed_filter.status = AlertStatus::DISMISSED;
    auto dismissed_alerts = alert_manager_->get_alerts(dismissed_filter);
    ASSERT_GE(dismissed_alerts.size(), 3);
}

TEST_F(AlertManagerTest, GetAlertCounts) {
    // Create alerts with different severities
    Alert alert1;
    alert1.severity = AlertSeverity::INFO;
    alert1.category = AlertCategory::CPU;
    alert1.source = "test";
    alert1.message = "Info alert";
    alert1.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert1);
    
    Alert alert2;
    alert2.severity = AlertSeverity::WARNING;
    alert2.category = AlertCategory::MEMORY;
    alert2.source = "test";
    alert2.message = "Warning alert";
    alert2.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert2);
    
    Alert alert3;
    alert3.severity = AlertSeverity::ERROR;
    alert3.category = AlertCategory::DISK;
    alert3.source = "test";
    alert3.message = "Error alert";
    alert3.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert3);
    
    auto counts = alert_manager_->get_alert_counts();
    ASSERT_EQ(counts["info"], 1);
    ASSERT_EQ(counts["warning"], 1);
    ASSERT_EQ(counts["error"], 1);
    ASSERT_EQ(counts["total"], 3);
}

TEST_F(AlertManagerTest, AlertJsonConversion) {
    Alert alert;
    alert.uuid = AlertManager::generate_uuid();
    alert.severity = AlertSeverity::CRITICAL;
    alert.category = AlertCategory::CPU;
    alert.source = "test_source";
    alert.message = "Critical alert";
    alert.description = "Test description";
    alert.status = AlertStatus::ACTIVE;
    alert.timestamp = std::chrono::system_clock::now();
    
    json j = alert.to_json();
    ASSERT_EQ(j["uuid"], alert.uuid);
    ASSERT_EQ(j["severity"], static_cast<int>(AlertSeverity::CRITICAL));
    ASSERT_EQ(j["severity_name"], "critical");
    ASSERT_EQ(j["message"], "Critical alert");
    
    Alert restored = Alert::from_json(j);
    ASSERT_EQ(restored.uuid, alert.uuid);
    ASSERT_EQ(restored.severity, AlertSeverity::CRITICAL);
    ASSERT_EQ(restored.message, "Critical alert");
}

TEST_F(AlertManagerTest, ExcludeDismissedAlerts) {
    Alert alert1;
    alert1.severity = AlertSeverity::WARNING;
    alert1.category = AlertCategory::CPU;
    alert1.source = "test";
    alert1.message = "Active alert";
    alert1.status = AlertStatus::ACTIVE;
    auto created1 = alert_manager_->create_alert(alert1);
    
    Alert alert2;
    alert2.severity = AlertSeverity::WARNING;
    alert2.category = AlertCategory::CPU;
    alert2.source = "test";
    alert2.message = "Dismissed alert";
    alert2.status = AlertStatus::ACTIVE;
    auto created2 = alert_manager_->create_alert(alert2);
    
    alert_manager_->dismiss_alert(created2->uuid);
    
    // Default filter should exclude dismissed
    AlertFilter filter;
    auto alerts = alert_manager_->get_alerts(filter);
    ASSERT_EQ(alerts.size(), 1);
    ASSERT_EQ(alerts[0].uuid, created1->uuid);
}
