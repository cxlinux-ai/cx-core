/**
 * @file http_llm_client.cpp
 * @brief HTTP client implementation for LLM API calls
 */

#include "cortexd/llm/http_llm_client.h"
#include "cortexd/logger.h"

#include <curl/curl.h>
#include <nlohmann/json.hpp>
#include <sstream>
#include <vector>

using json = nlohmann::json;

namespace cortexd {

HttpLLMClient::HttpLLMClient() {
    // Initialize CURL globally (should be done once)
    static bool curl_initialized = false;
    if (!curl_initialized) {
        curl_global_init(CURL_GLOBAL_ALL);
        curl_initialized = true;
    }
}

HttpLLMClient::~HttpLLMClient() {
    // Note: curl_global_cleanup() should be called at program exit
}

void HttpLLMClient::configure(LLMBackendType type, 
                               const std::string& base_url,
                               const std::string& api_key) {
    backend_type_ = type;
    api_key_ = api_key;
    
    switch (type) {
        case LLMBackendType::LOCAL:
            base_url_ = base_url.empty() ? "http://127.0.0.1:8085" : base_url;
            LOG_INFO("HttpLLMClient", "Configured for local llama-server at: " + base_url_);
            break;
        case LLMBackendType::CLOUD_CLAUDE:
            base_url_ = "https://api.anthropic.com";
            LOG_INFO("HttpLLMClient", "Configured for Claude API");
            break;
        case LLMBackendType::CLOUD_OPENAI:
            base_url_ = "https://api.openai.com";
            LOG_INFO("HttpLLMClient", "Configured for OpenAI API");
            break;
        default:
            base_url_ = "";
            LOG_INFO("HttpLLMClient", "LLM backend disabled");
            break;
    }
}

bool HttpLLMClient::is_configured() const {
    if (backend_type_ == LLMBackendType::NONE) {
        return false;
    }
    if (backend_type_ == LLMBackendType::LOCAL) {
        return !base_url_.empty();
    }
    // Cloud backends require API key
    return !api_key_.empty();
}

size_t HttpLLMClient::write_callback(char* ptr, size_t size, size_t nmemb, std::string* data) {
    data->append(ptr, size * nmemb);
    return size * nmemb;
}

std::string HttpLLMClient::http_post(const std::string& url,
                                      const std::string& body,
                                      const std::vector<std::string>& headers) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        LOG_ERROR("HttpLLMClient", "Failed to initialize CURL");
        return "";
    }
    
    std::string response;
    struct curl_slist* header_list = nullptr;
    
    // Set headers
    for (const auto& header : headers) {
        header_list = curl_slist_append(header_list, header.c_str());
    }
    
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_POST, 1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, header_list);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 180L);  // 180 second timeout (LLM inference is slow)
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    
    CURLcode res = curl_easy_perform(curl);
    
    if (header_list) {
        curl_slist_free_all(header_list);
    }
    
    if (res != CURLE_OK) {
        LOG_ERROR("HttpLLMClient", "CURL error: " + std::string(curl_easy_strerror(res)));
        curl_easy_cleanup(curl);
        return "";
    }
    
    curl_easy_cleanup(curl);
    return response;
}

HttpLLMResult HttpLLMClient::generate(const std::string& prompt,
                                       int max_tokens,
                                       float temperature) {
    switch (backend_type_) {
        case LLMBackendType::LOCAL:
            return call_local_llama(prompt, max_tokens, temperature);
        case LLMBackendType::CLOUD_CLAUDE:
            return call_claude_api(prompt, max_tokens, temperature);
        case LLMBackendType::CLOUD_OPENAI:
            return call_openai_api(prompt, max_tokens, temperature);
        default:
            return {false, "", "LLM backend not configured", 0};
    }
}

HttpLLMResult HttpLLMClient::call_local_llama(const std::string& prompt,
                                               int max_tokens,
                                               float temperature) {
    HttpLLMResult result;
    
    // Format prompt for Llama-2-Chat model with proper system message
    // The prompt already contains the full instruction, so we use simple INST tags
    std::string formatted_prompt = "<s>[INST] <<SYS>>\nYou are a helpful Linux system administrator AI. Give direct, actionable advice. Do not ask questions or request clarification. Just provide the answer.\n<</SYS>>\n\n" + prompt + " [/INST]";
    
    // Use native llama.cpp /completion endpoint (more reliable than OpenAI-compatible)
    json request_body = {
        {"prompt", formatted_prompt},
        {"n_predict", max_tokens},
        {"temperature", temperature},
        {"stop", json::array({"</s>", "[INST]", "[/INST]"})},  // Stop sequences
        {"stream", false}
    };
    
    std::string url = base_url_ + "/completion";
    std::vector<std::string> headers = {
        "Content-Type: application/json"
    };
    
    LOG_DEBUG("HttpLLMClient", "Calling local llama-server: " + url);
    
    std::string response = http_post(url, request_body.dump(), headers);
    
    if (response.empty()) {
        result.success = false;
        result.error = "Failed to connect to llama-server. Is cortex-llm.service running?";
        return result;
    }
    
    try {
        json resp_json = json::parse(response);
        
        if (resp_json.contains("error")) {
            result.success = false;
            if (resp_json["error"].is_object() && resp_json["error"].contains("message")) {
                result.error = resp_json["error"]["message"].get<std::string>();
            } else {
                result.error = resp_json["error"].dump();
            }
            return result;
        }
        
        // Native llama.cpp response format
        if (resp_json.contains("content")) {
            result.success = true;
            result.output = resp_json["content"].get<std::string>();
            
            // Clean up the response - remove prompt echoes and instruction-like text
            // Common patterns the LLM might echo back
            std::vector<std::string> bad_patterns = {
                "Please provide",
                "Please note",
                "Please give",
                "You are a",
                "As a Linux",
                "As an AI",
                "I'd be happy to",
                "Here's my response",
                "Here is my response",
                "Let me help",
                "I can help",
                "(2-3 sentences",
                "sentences max)",
                "Be specific and concise",
                "brief, actionable",
                "Hint:",
                "Note:"
            };
            
            // Remove lines that contain prompt-like patterns
            std::string cleaned;
            std::istringstream stream(result.output);
            std::string line;
            bool found_good_content = false;
            
            while (std::getline(stream, line)) {
                bool is_bad_line = false;
                for (const auto& pattern : bad_patterns) {
                    if (line.find(pattern) != std::string::npos) {
                        is_bad_line = true;
                        break;
                    }
                }
                if (!is_bad_line && !line.empty()) {
                    // Skip lines that are just whitespace
                    size_t first_non_space = line.find_first_not_of(" \t");
                    if (first_non_space != std::string::npos) {
                        if (found_good_content) cleaned += "\n";
                        cleaned += line;
                        found_good_content = true;
                    }
                }
            }
            
            result.output = cleaned;
            
            // Final trim
            size_t start = result.output.find_first_not_of(" \n\r\t");
            size_t end = result.output.find_last_not_of(" \n\r\t");
            if (start != std::string::npos && end != std::string::npos) {
                result.output = result.output.substr(start, end - start + 1);
            } else {
                result.output = "";  // All content was filtered out
            }
        } else {
            result.success = false;
            result.error = "Invalid response format from llama-server";
            LOG_ERROR("HttpLLMClient", "Response: " + response.substr(0, 200));
        }
    } catch (const json::exception& e) {
        result.success = false;
        result.error = "Failed to parse llama-server response: " + std::string(e.what());
        LOG_ERROR("HttpLLMClient", result.error);
    }
    
    return result;
}

HttpLLMResult HttpLLMClient::call_claude_api(const std::string& prompt,
                                              int max_tokens,
                                              float /*temperature*/) {
    HttpLLMResult result;
    
    if (api_key_.empty()) {
        result.success = false;
        result.error = "Claude API key not configured";
        return result;
    }
    
    // Build Claude API request
    json request_body = {
        {"model", "claude-sonnet-4-20250514"},
        {"max_tokens", max_tokens},
        {"messages", json::array({
            {{"role", "user"}, {"content", prompt}}
        })}
    };
    
    std::string url = base_url_ + "/v1/messages";
    std::vector<std::string> headers = {
        "Content-Type: application/json",
        "x-api-key: " + api_key_,
        "anthropic-version: 2023-06-01"
    };
    
    LOG_DEBUG("HttpLLMClient", "Calling Claude API");
    
    std::string response = http_post(url, request_body.dump(), headers);
    
    if (response.empty()) {
        result.success = false;
        result.error = "Failed to connect to Claude API";
        return result;
    }
    
    try {
        json resp_json = json::parse(response);
        
        if (resp_json.contains("error")) {
            result.success = false;
            result.error = resp_json["error"]["message"].get<std::string>();
            return result;
        }
        
        if (resp_json.contains("content") && !resp_json["content"].empty()) {
            result.success = true;
            result.output = resp_json["content"][0]["text"].get<std::string>();
        } else {
            result.success = false;
            result.error = "Invalid response format from Claude API";
        }
    } catch (const json::exception& e) {
        result.success = false;
        result.error = "Failed to parse Claude response: " + std::string(e.what());
        LOG_ERROR("HttpLLMClient", result.error);
    }
    
    return result;
}

HttpLLMResult HttpLLMClient::call_openai_api(const std::string& prompt,
                                              int max_tokens,
                                              float temperature) {
    HttpLLMResult result;
    
    if (api_key_.empty()) {
        result.success = false;
        result.error = "OpenAI API key not configured";
        return result;
    }
    
    // Build OpenAI API request
    json request_body = {
        {"model", "gpt-4"},
        {"messages", json::array({
            {{"role", "user"}, {"content", prompt}}
        })},
        {"max_tokens", max_tokens},
        {"temperature", temperature}
    };
    
    std::string url = base_url_ + "/v1/chat/completions";
    std::vector<std::string> headers = {
        "Content-Type: application/json",
        "Authorization: Bearer " + api_key_
    };
    
    LOG_DEBUG("HttpLLMClient", "Calling OpenAI API");
    
    std::string response = http_post(url, request_body.dump(), headers);
    
    if (response.empty()) {
        result.success = false;
        result.error = "Failed to connect to OpenAI API";
        return result;
    }
    
    try {
        json resp_json = json::parse(response);
        
        if (resp_json.contains("error")) {
            result.success = false;
            result.error = resp_json["error"]["message"].get<std::string>();
            return result;
        }
        
        if (resp_json.contains("choices") && !resp_json["choices"].empty()) {
            result.success = true;
            result.output = resp_json["choices"][0]["message"]["content"].get<std::string>();
        } else {
            result.success = false;
            result.error = "Invalid response format from OpenAI API";
        }
    } catch (const json::exception& e) {
        result.success = false;
        result.error = "Failed to parse OpenAI response: " + std::string(e.what());
        LOG_ERROR("HttpLLMClient", result.error);
    }
    
    return result;
}

} // namespace cortexd

