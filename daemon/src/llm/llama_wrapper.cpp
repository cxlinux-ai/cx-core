#include "llm_wrapper.h"
#include "logging.h"
#include <chrono>
#include <cerrno>
#include <cstring>
#include <fstream>

// Include real llama.cpp header
#include <llama.h>

namespace cortex {
namespace daemon {

InferenceQueue::InferenceQueue(std::shared_ptr<LLMWrapper> llm)
    : llm_(llm), running_(false) {
    rate_limiter_.last_reset = std::chrono::system_clock::now();
    Logger::info("InferenceQueue", "Initialized");
}

InferenceQueue::~InferenceQueue() {
    stop();
}

bool InferenceQueue::check_rate_limit() {
    // FIX #6: Rate limiting
    auto now = std::chrono::system_clock::now();
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        now - rate_limiter_.last_reset).count();
    
    if (elapsed >= RateLimiter::WINDOW_SIZE_MS) {
        rate_limiter_.requests_in_window = 0;
        rate_limiter_.last_reset = now;
        return true;
    }
    
    if (rate_limiter_.requests_in_window < RateLimiter::MAX_REQUESTS_PER_SECOND) {
        rate_limiter_.requests_in_window++;
        return true;
    }
    
    return false;
}

bool InferenceQueue::enqueue(const InferenceRequest& request, InferenceResult& error) {
    // Rate limiting check
    if (!check_rate_limit()) {
        error.error = "Rate limit exceeded (max 100 requests/second)";
        error.success = false;
        Logger::warn("InferenceQueue", error.error);
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        // Queue limit enforcement with client notification
        if (queue_.size() >= 100) {
            error.error = "Inference queue full (max 100 pending)";
            error.success = false;
            Logger::warn("InferenceQueue", error.error);
            return false;
        }
        queue_.push(request);
    }
    queue_cv_.notify_one();
    return true;
}

InferenceResult InferenceQueue::get_last_result() const {
    return last_result_;
}

void InferenceQueue::start() {
    if (running_) {
        return;
    }

    running_ = true;
    worker_thread_ = std::make_unique<std::thread>([this] { process_queue(); });
    Logger::info("InferenceQueue", "Worker started");
}

void InferenceQueue::stop() {
    running_ = false;
    queue_cv_.notify_all();

    if (worker_thread_ && worker_thread_->joinable()) {
        worker_thread_->join();
    }

    Logger::info("InferenceQueue", "Worker stopped");
}

size_t InferenceQueue::get_queue_size() const {
    // Cast away const for thread-safe read
    auto* mutable_this = const_cast<InferenceQueue*>(this);
    std::lock_guard<std::mutex> lock(mutable_this->queue_mutex_);
    return queue_.size();
}

void InferenceQueue::process_queue() {
    while (running_) {
        InferenceRequest request;

        {
            std::unique_lock<std::mutex> lock(queue_mutex_);
            queue_cv_.wait(lock, [this] { return !queue_.empty() || !running_; });

            if (!running_) break;
            if (queue_.empty()) continue;

            request = queue_.front();
            queue_.pop();
        }

        // Process request
        if (llm_ && llm_->is_loaded()) {
            auto start = std::chrono::high_resolution_clock::now();
            InferenceResult result = llm_->infer(request);
            auto end = std::chrono::high_resolution_clock::now();

            result.inference_time_ms = std::chrono::duration<float, std::milli>(end - start).count();
            last_result_ = result;

            Logger::debug("InferenceQueue", "Processed request in " + 
                         std::to_string(result.inference_time_ms) + "ms");
        }
    }
}

// LlamaWrapper implementation
LlamaWrapper::LlamaWrapper() 
    : ctx_(nullptr), model_(nullptr), loaded_(false), n_threads_(DEFAULT_THREADS) {
    Logger::info("LlamaWrapper", "Initialized with " + std::to_string(n_threads_) + " threads");
}

LlamaWrapper::~LlamaWrapper() {
    unload_model();
}

bool LlamaWrapper::load_model(const std::string& model_path) {
    std::lock_guard<std::mutex> lock(llm_mutex_);

    if (loaded_) {
        Logger::warn("LlamaWrapper", "Model already loaded");
        return true;
    }

    Logger::info("LlamaWrapper", "Loading model from " + model_path);

    try {
        // Check if file exists
        if (!std::ifstream(model_path).good()) {
            Logger::error("LlamaWrapper", "Model file not accessible: " + model_path);
            return false;
        }

        // Get default model parameters
        llama_model_params model_params = llama_model_default_params();
        
        Logger::info("LlamaWrapper", "Loading model with llama_model_load_from_file");
        
        // Load model using new API
        model_ = llama_model_load_from_file(model_path.c_str(), model_params);
        if (!model_) {
            Logger::error("LlamaWrapper", "llama_model_load_from_file returned NULL");
            Logger::error("LlamaWrapper", "This usually means:");
            Logger::error("LlamaWrapper", "  1. File is not a valid GGUF model");
            Logger::error("LlamaWrapper", "  2. Incompatible model format");
            Logger::error("LlamaWrapper", "  3. Insufficient memory");
            return false;
        }

        // Get default context parameters and configure
        llama_context_params ctx_params = llama_context_default_params();
        ctx_params.n_ctx = 512;
        ctx_params.n_threads = n_threads_;
        
        // Create context with model
        ctx_ = llama_new_context_with_model(model_, ctx_params);
        if (!ctx_) {
            Logger::error("LlamaWrapper", "Failed to create context for model");
            llama_free_model(model_);
            model_ = nullptr;
            return false;
        }

        loaded_ = true;
        Logger::info("LlamaWrapper", 
            "Model loaded successfully: " + model_path + 
            " (threads=" + std::to_string(n_threads_) + 
            ", ctx=512, mmap=true)");
        return true;
    } catch (const std::exception& e) {
        Logger::error("LlamaWrapper", "Exception loading model: " + std::string(e.what()));
        loaded_ = false;
        return false;
    }
}

bool LlamaWrapper::is_loaded() const {
    // Simple check without locking to avoid deadlock with monitoring thread
    // Reading a bool is atomic on most architectures
    return loaded_;
}

InferenceResult LlamaWrapper::infer(const InferenceRequest& request) {
    std::lock_guard<std::mutex> lock(llm_mutex_);

    InferenceResult result;
    result.request_id = request.callback_id;
    result.success = false;

    if (!loaded_ || !ctx_ || !model_) {
        result.error = "Model not loaded";
        Logger::warn("LlamaWrapper", result.error);
        return result;
    }

    // Input validation on prompt size
    if (request.prompt.size() > 8192) {
        result.error = "Prompt exceeds maximum size (8192 bytes)";
        Logger::warn("LlamaWrapper", result.error);
        return result;
    }

    if (request.prompt.empty()) {
        result.error = "Prompt cannot be empty";
        Logger::warn("LlamaWrapper", result.error);
        return result;
    }

    if (request.max_tokens <= 0) {
        result.error = "max_tokens must be positive";
        Logger::warn("LlamaWrapper", result.error);
        return result;
    }

    try {
        // TODO: Implement proper inference using llama.cpp's decode API
        // For now, just return an error as inference is not yet implemented
        result.error = "Inference not yet implemented - model loaded but inference requires llama_decode API integration";
        Logger::warn("LlamaWrapper", result.error);
        return result;
        
        /* Old inference code using deprecated API:
        // Start inference with timeout tracking
        auto start_time = std::chrono::high_resolution_clock::now();
        auto timeout_duration = std::chrono::seconds(30);

        // Run inference on the prompt
        const char* prompt = request.prompt.c_str();
        int max_tokens = std::min(request.max_tokens, 256);

        // Call llama.cpp inference with timeout check and error details
        int tokens_generated = llama_generate(ctx_, prompt, max_tokens);
        
        auto elapsed = std::chrono::high_resolution_clock::now() - start_time;
        if (elapsed > timeout_duration) {
            result.error = "Inference timeout exceeded (30 seconds)";
            Logger::error("LlamaWrapper", result.error);
            return result;
        }

        if (tokens_generated < 0) {
            result.error = "Inference generation failed: " + std::string(strerror(errno));
            Logger::error("LlamaWrapper", result.error);
            return result;
        }

        // Convert tokens to string output with safety checks (prevent infinite loop)
        std::string output;
        for (int i = 0; i < tokens_generated && i < max_tokens; i++) {
            const char* token_str = llama_token_to_str(ctx_, i);
            if (!token_str) {
                Logger::debug("LlamaWrapper", "Null token at index " + std::to_string(i));
                break;
            }
            output += token_str;

            // Timeout check between tokens
            auto current_elapsed = std::chrono::high_resolution_clock::now() - start_time;
            if (current_elapsed > timeout_duration) {
                Logger::warn("LlamaWrapper", "Timeout during token generation");
                break;
            }
        }
        */
    } catch (const std::exception& e) {
        result.error = "Inference exception: " + std::string(e.what());
        Logger::error("LlamaWrapper", result.error);
    }

    return result;
}
size_t LlamaWrapper::get_memory_usage() {
    std::lock_guard<std::mutex> lock(llm_mutex_);
    
    if (!ctx_) {
        return 0;
    }

    // Estimate memory usage:
    // Model parameters + context buffers + embeddings
    // For a rough estimate: context_size * model_width * bytes_per_param
    // Typical: 512 context * 768 embeddings * 4 bytes = ~1.5MB
    // Plus model weights (varies by model size)
    
    // This is a conservative estimate
    size_t estimated_memory = 512 * 768 * 4;  // Context embeddings
    
    Logger::debug("LlamaWrapper", "Estimated memory: " + std::to_string(estimated_memory) + " bytes");
    return estimated_memory;
}

void LlamaWrapper::unload_model() {
    std::lock_guard<std::mutex> lock(llm_mutex_);
    
    if (ctx_) {
        llama_free(ctx_);
        ctx_ = nullptr;
        Logger::debug("LlamaWrapper", "Context freed");
    }

    if (model_) {
        llama_model_free(model_);  // Use non-deprecated API
        model_ = nullptr;
        Logger::debug("LlamaWrapper", "Model freed");
    }

    loaded_ = false;
    Logger::info("LlamaWrapper", "Model unloaded");
}

void LlamaWrapper::set_n_threads(int n_threads) {
    std::lock_guard<std::mutex> lock(llm_mutex_);
    n_threads_ = std::max(1, n_threads);
    Logger::info("LlamaWrapper", "Thread count set to " + std::to_string(n_threads_));
}

int LlamaWrapper::get_n_threads() const {
    auto* mutable_this = const_cast<LlamaWrapper*>(this);
    std::lock_guard<std::mutex> lock(mutable_this->llm_mutex_);
    return n_threads_;
}

} // namespace daemon
} // namespace cortex
