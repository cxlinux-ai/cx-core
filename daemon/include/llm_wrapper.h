#pragma once

#include <string>
#include <memory>
#include <queue>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>

// Forward declare llama.cpp types
struct llama_context;
struct llama_model;

namespace cortex {
namespace daemon {

// LLM inference queue item
struct InferenceRequest {
    std::string prompt;
    int max_tokens = 256;
    float temperature = 0.7f;
    std::string callback_id;
};

struct InferenceResult {
    std::string request_id;
    std::string output;
    float inference_time_ms;
    bool success;
    std::string error;
};

// LLM wrapper interface
class LLMWrapper {
public:
    virtual ~LLMWrapper() = default;

    // Load model from path
    virtual bool load_model(const std::string& model_path) = 0;

    // Check if model is loaded
    virtual bool is_loaded() const = 0;

    // Run inference
    virtual InferenceResult infer(const InferenceRequest& request) = 0;

    // Get memory usage
    virtual size_t get_memory_usage() = 0;

    // Unload model
    virtual void unload_model() = 0;
};

// Rate limiter for inference requests
struct RateLimiter {
    std::chrono::system_clock::time_point last_reset;
    int requests_in_window = 0;
    static constexpr int MAX_REQUESTS_PER_SECOND = 100;
    static constexpr int WINDOW_SIZE_MS = 1000;
};

// Inference queue processor
class InferenceQueue {
public:
    InferenceQueue(std::shared_ptr<LLMWrapper> llm);
    ~InferenceQueue();

    // Enqueue inference request (returns false if queue full or rate limited)
    bool enqueue(const InferenceRequest& request, InferenceResult& error);

    // Get last result
    InferenceResult get_last_result() const;

    // Start processing queue
    void start();

    // Stop processing
    void stop();

    // Get queue size
    size_t get_queue_size() const;

private:
    std::shared_ptr<LLMWrapper> llm_;
    std::queue<InferenceRequest> queue_;
    std::unique_ptr<std::thread> worker_thread_;
    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::atomic<bool> running_;
    InferenceResult last_result_;
    RateLimiter rate_limiter_;
    static constexpr size_t MAX_PROMPT_SIZE = 8192;

    void process_queue();
    bool check_rate_limit();
};

// Concrete llama.cpp wrapper
class LlamaWrapper : public LLMWrapper {
public:
    LlamaWrapper();
    ~LlamaWrapper();

    bool load_model(const std::string& model_path) override;
    bool is_loaded() const override;
    InferenceResult infer(const InferenceRequest& request) override;
    size_t get_memory_usage() override;
    void unload_model() override;

    // Additional llama.cpp specific methods
    void set_n_threads(int n_threads);
    int get_n_threads() const;

private:
    llama_context* ctx_;
    llama_model* model_;
    bool loaded_;
    std::mutex llm_mutex_;
    int n_threads_;
    static constexpr int DEFAULT_THREADS = 4;
};

} // namespace daemon
} // namespace cortex
