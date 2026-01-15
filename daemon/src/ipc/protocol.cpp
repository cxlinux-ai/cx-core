/**
 * @file protocol.cpp
 * @brief IPC protocol implementation
 */

 #include "cortexd/ipc/protocol.h"
 #include "cortexd/logger.h"
 
 namespace cortexd {
 
 std::optional<Request> Request::parse(const std::string& raw) {
     try {
         auto j = json::parse(raw);
         
         Request req;
         
         // Method is required
         if (!j.contains("method") || !j["method"].is_string()) {
             LOG_WARN("Protocol", "Request missing 'method' field");
             return std::nullopt;
         }
         req.method = j["method"].get<std::string>();
         
         // Params are optional
         if (j.contains("params")) {
             req.params = j["params"];
         } else {
             req.params = json::object();
         }
         
         // ID is optional
         if (j.contains("id")) {
             if (j["id"].is_string()) {
                 req.id = j["id"].get<std::string>();
             } else if (j["id"].is_number()) {
                 req.id = std::to_string(j["id"].get<int>());
             }
         }
         
         return req;
         
     } catch (const json::exception& e) {
         LOG_WARN("Protocol", "JSON parse error: " + std::string(e.what()));
         return std::nullopt;
     }
 }
 
 std::string Request::to_json() const {
     json j;
     j["method"] = method;
     j["params"] = params;
     if (id) {
         j["id"] = *id;
     }
     return j.dump();
 }
 
 std::string Response::to_json() const {
     json j;
     j["success"] = success;
     j["timestamp"] = Clock::to_time_t(Clock::now());
     
     if (success) {
         j["result"] = result;
     } else {
         j["error"] = {
             {"message", error},
             {"code", error_code}
         };
     }
     
     return j.dump();
 }
 
 Response Response::ok(json result) {
     Response resp;
     resp.success = true;
     resp.result = std::move(result);
     return resp;
 }
 
 Response Response::err(const std::string& message, int code) {
     Response resp;
     resp.success = false;
     resp.error = message;
     resp.error_code = code;
     return resp;
 }
 
 } // namespace cortexd
 