/**
 * @file protocol.h
 * @brief JSON-RPC protocol definitions for IPC
 */

 #pragma once

 #include "cortexd/common.h"
 #include <string>
 #include <optional>
 
 namespace cortexd {
 
 /**
  * @brief IPC request structure
  */
 struct Request {
     std::string method;
     json params;
     std::optional<std::string> id;
     
     /**
      * @brief Parse request from JSON string
      * @param raw Raw JSON string
      * @return Request if valid, std::nullopt on parse error
      */
     static std::optional<Request> parse(const std::string& raw);
     
     /**
      * @brief Serialize to JSON string
      */
     std::string to_json() const;
 };
 
 /**
  * @brief IPC response structure
  */
 struct Response {
     bool success = false;
     json result;
     std::string error;
     int error_code = 0;
     
     /**
      * @brief Serialize to JSON string
      */
     std::string to_json() const;
     
     /**
      * @brief Create success response
      */
     static Response ok(json result = json::object());
     
     /**
      * @brief Create error response
      */
     static Response err(const std::string& message, int code = -1);
 };
 
 /**
  * @brief Supported IPC methods
  */
 namespace Methods {
     // Status and health
     constexpr const char* STATUS = "status";
     constexpr const char* HEALTH = "health";
     constexpr const char* VERSION = "version";
     
     // Alert management
     constexpr const char* ALERTS = "alerts";
     constexpr const char* ALERTS_GET = "alerts.get";
     constexpr const char* ALERTS_ACK = "alerts.acknowledge";
     constexpr const char* ALERTS_DISMISS = "alerts.dismiss";
     
     // Configuration
     constexpr const char* CONFIG_GET = "config.get";
     constexpr const char* CONFIG_RELOAD = "config.reload";
     
     // LLM operations
     constexpr const char* LLM_STATUS = "llm.status";
     constexpr const char* LLM_LOAD = "llm.load";
     constexpr const char* LLM_UNLOAD = "llm.unload";
     constexpr const char* LLM_INFER = "llm.infer";
     
     // Daemon control
     constexpr const char* SHUTDOWN = "shutdown";
     constexpr const char* PING = "ping";
 }
 
 /**
  * @brief Error codes for IPC responses
  * 
  * JSON-RPC reserves -32768 to -32000 for standard errors.
  * Custom application errors use positive integers (1-999).
  */
 namespace ErrorCodes {
     // JSON-RPC standard errors (reserved range: -32768 to -32000)
     constexpr int PARSE_ERROR = -32700;
     constexpr int INVALID_REQUEST = -32600;
     constexpr int METHOD_NOT_FOUND = -32601;
     constexpr int INVALID_PARAMS = -32602;
     constexpr int INTERNAL_ERROR = -32603;
     
     // Custom application errors (non-reserved range: 1-999)
     constexpr int LLM_NOT_LOADED = 100;
     constexpr int LLM_BUSY = 101;
     constexpr int RATE_LIMITED = 102;
     constexpr int ALERT_NOT_FOUND = 103;
     constexpr int CONFIG_ERROR = 104;
 }
 
 } // namespace cortexd
 