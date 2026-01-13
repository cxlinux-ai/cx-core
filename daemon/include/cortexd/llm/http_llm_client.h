/**
 * @file http_llm_client.h
 * @brief HTTP client for LLM API calls (local llama-server or cloud APIs)
 */

#pragma once

#include <string>
#include <optional>
#include <functional>

namespace cortexd {

/**
 * @brief LLM backend type
 */
enum class LLMBackendType {
    NONE,           // No LLM configured
    LOCAL,          // Local llama-server (cortex-llm.service)
    CLOUD_CLAUDE,   // Anthropic Claude API
    CLOUD_OPENAI    // OpenAI API
};

/**
 * @brief Result of an LLM inference request
 */
struct HttpLLMResult {
    bool success = false;
    std::string output;
    std::string error;
    int status_code = 0;
};

/**
 * @brief HTTP client for making LLM API calls
 * 
 * Supports:
 * - Local llama-server (OpenAI-compatible API at localhost:8085)
 * - Cloud APIs (Claude, OpenAI)
 */
class HttpLLMClient {
public:
    HttpLLMClient();
    ~HttpLLMClient();
    
    /**
     * @brief Set the LLM backend to use
     * @param type Backend type
     * @param base_url API base URL (for local) or empty for cloud defaults
     * @param api_key API key (for cloud backends)
     */
    void configure(LLMBackendType type, 
                   const std::string& base_url = "",
                   const std::string& api_key = "");
    
    /**
     * @brief Check if client is configured and ready
     */
    bool is_configured() const;
    
    /**
     * @brief Get the current backend type
     */
    LLMBackendType get_backend_type() const { return backend_type_; }
    
    /**
     * @brief Generate text using the configured LLM backend
     * @param prompt The prompt to send
     * @param max_tokens Maximum tokens to generate
     * @param temperature Sampling temperature (0.0-1.0)
     * @return Result containing success status and output/error
     */
    HttpLLMResult generate(const std::string& prompt,
                           int max_tokens = 150,
                           float temperature = 0.3f);

private:
    LLMBackendType backend_type_ = LLMBackendType::NONE;
    std::string base_url_;
    std::string api_key_;
    
    // HTTP request helpers
    HttpLLMResult call_local_llama(const std::string& prompt, int max_tokens, float temperature);
    HttpLLMResult call_claude_api(const std::string& prompt, int max_tokens, float temperature);
    HttpLLMResult call_openai_api(const std::string& prompt, int max_tokens, float temperature);
    
    // CURL helper
    static size_t write_callback(char* ptr, size_t size, size_t nmemb, std::string* data);
    std::string http_post(const std::string& url, 
                          const std::string& body,
                          const std::vector<std::string>& headers);
};

} // namespace cortexd

