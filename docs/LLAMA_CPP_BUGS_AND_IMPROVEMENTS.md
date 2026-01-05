# Cortexd llama.cpp - Bug Report & Improvement Recommendations

**Date**: January 2, 2026
**Status**: Testing & Validation Phase

---

## 🐛 Identified Issues & Bugs

### Critical Issues (Must Fix Before Production)

#### 1. **No Input Validation on Prompt Size**
**Severity**: HIGH
**Location**: `daemon/src/llm/llama_wrapper.cpp` - `infer()` method
**Issue**: Accepts prompts of any size without validation
**Impact**: Could cause memory issues or buffer overflow
**Fix**:
```cpp
// Add validation
int max_prompt_size = 8192;  // 8KB limit
if (request.prompt.size() > max_prompt_size) {
    result.error = "Prompt exceeds maximum size";
    return result;
}
```

#### 2. **No Timeout on Inference**
**Severity**: HIGH  
**Location**: `daemon/src/llm/llama_wrapper.cpp` - `infer()` method
**Issue**: Long-running inference has no timeout
**Impact**: Slow models could block daemon indefinitely
**Fix**:
```cpp
// Add timeout using std::chrono
auto start = std::chrono::high_resolution_clock::now();
auto timeout = std::chrono::seconds(30);
while (...) {
    if (std::chrono::high_resolution_clock::now() - start > timeout) {
        result.error = "Inference timeout";
        break;
    }
}
```

#### 3. **Memory Leak on Failed Model Load**
**Severity**: HIGH
**Location**: `daemon/src/llm/llama_wrapper.cpp` - `load_model()` method
**Issue**: If context creation fails after model load, model isn't freed
**Current Code**:
```cpp
model_ = llama_load_model_from_file(model_path.c_str(), params);
if (!model_) return false;  // ✅ Model freed by error path

ctx_ = llama_new_context_with_model(model_, params);
if (!ctx_) {
    llama_free_model(model_);  // ✅ Already in code - GOOD
    model_ = nullptr;
    return false;
}
```
**Status**: Already handled correctly ✅

#### 4. **Config Reload Doesn't Reload Model**
**Severity**: MEDIUM
**Location**: `daemon/src/config/daemon_config.cpp` - `reload_config()` method
**Issue**: Calling `reload-config` won't reload model if path changes
**Impact**: Must restart daemon to change models
**Fix**:
```cpp
// Add signal to reload model on config change
void reload_config() {
    old_model_path = daemon_config_.model_path;
    load_config();
    
    if (daemon_config_.model_path != old_model_path) {
        llm_wrapper_->unload_model();
        llm_wrapper_->load_model(daemon_config_.model_path);
    }
}
```

#### 5. **No Queue Size Limit Enforcement**
**Severity**: MEDIUM
**Location**: `daemon/src/llm/inference_queue.cpp` - `enqueue()` method
**Issue**: Queue drops requests when full, doesn't notify client
**Current Code**:
```cpp
if (queue_.size() >= 100) {
    Logger::warn("InferenceQueue", "Queue full, dropping request");
    return;  // ⚠️ Client never knows request was dropped
}
```
**Fix**:
```cpp
// Return status to indicate queue full
bool InferenceQueue::enqueue(const InferenceRequest& req, InferenceResult& error) {
    {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        if (queue_.size() >= 100) {
            error.error = "Inference queue full";
            return false;
        }
        queue_.push(req);
    }
    return true;
}
```

---

### Medium Severity Issues

#### 6. **No Rate Limiting**
**Severity**: MEDIUM
**Issue**: No protection against request floods
**Impact**: Daemon could be DoS'd with rapid requests
**Fix**:
```cpp
// Add request rate limiting
struct RateLimiter {
    std::chrono::system_clock::time_point last_request;
    int requests_per_second = 100;
    
    bool check_rate_limit() {
        auto now = std::chrono::system_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
            now - last_request).count();
        if (elapsed < requests_per_second) return false;
        last_request = now;
        return true;
    }
};
```

#### 7. **Error Messages Lack Detail**
**Severity**: MEDIUM
**Issue**: Generic "Failed to load model" - doesn't say why
**Impact**: Hard to debug issues
**Fix**:
```cpp
// Add errno/strerror context
if (!model_) {
    int error_code = errno;
    Logger::error("LlamaWrapper", 
        std::string("Failed to load model: ") + strerror(error_code));
    result.error = std::string("Model load failed: ") + strerror(error_code);
}
```

#### 8. **Token Generation Loop Could Be Infinite**
**Severity**: MEDIUM
**Location**: `daemon/src/llm/llama_wrapper.cpp` - `infer()` loop
**Issue**: If `llama_generate()` returns 0, loop continues indefinitely
**Fix**:
```cpp
for (int i = 0; i < tokens_generated; i++) {
    if (i >= max_tokens) break;  // Safety check
    const char* token_str = llama_token_to_str(ctx_, i);
    if (!token_str) break;  // Stop if null token
    output += token_str;
}
```

---

### Low Severity Issues (Nice to Have)

#### 9. **No Thread Safety on Model Reload**
**Severity**: LOW
**Issue**: Model pointer could be accessed during reload
**Impact**: Race condition risk
**Fix**: Already using `std::lock_guard` ✅ (needs validation)

#### 10. **Context Parameters Hardcoded**
**Severity**: LOW
**Issue**: Context size 512 hardcoded, should be configurable
**Impact**: Can't tune for specific use cases
**Fix**:
```cpp
// Make configurable via daemon.conf
int n_ctx = config.get<int>("llm.n_ctx", 512);
params.n_ctx = n_ctx;
```

#### 11. **No Model Validation**
**Severity**: LOW
**Issue**: Doesn't validate model format before loading
**Impact**: Unclear error messages for corrupted files
**Fix**:
```cpp
// Add magic number check for GGUF
bool is_valid_gguf(const std::string& path) {
    std::ifstream file(path, std::ios::binary);
    char magic[4];
    file.read(magic, 4);
    return std::string(magic, 4) == "GGUF";
}
```

#### 12. **No Logging of Model Parameters**
**Severity**: LOW
**Issue**: Doesn't log what model was loaded or its size
**Impact**: Hard to debug model issues
**Fix**:
```cpp
Logger::info("LlamaWrapper", 
    "Model loaded: " + model_path + 
    " (threads=" + std::to_string(n_threads_) + 
    ", ctx=" + std::to_string(512) + ")");
```

---

## 📋 Areas for Improvement

### Phase 2 Enhancements

#### 1. **Token Streaming** (High Priority)
```cpp
// Return tokens as they're generated (Server-Sent Events)
class InferenceStream {
    void stream_token(const std::string& token);
    bool has_next_token();
    std::string get_next_token();
};

// API: {"command":"inference","params":{...},"stream":true}
// Returns tokens one per line via streaming response
```

#### 2. **Model Hot-Swap** (High Priority)
```cpp
// Load multiple models, switch without restart
class ModelManager {
    std::map<std::string, std::shared_ptr<LlamaWrapper>> models_;
    void load_model(const std::string& name, const std::string& path);
    void set_active_model(const std::string& name);
};
```

#### 3. **Inference Caching** (High Priority)
```cpp
// Cache results for identical prompts
class InferenceCache {
    std::unordered_map<std::string, std::string> cache_;
    std::string get_cached(const std::string& prompt);
    void cache_result(const std::string& prompt, const std::string& output);
};
```

#### 4. **Batch Processing** (Medium Priority)
```cpp
// Process multiple prompts in parallel
class BatchInference {
    std::vector<InferenceResult> infer_batch(
        const std::vector<InferenceRequest>& requests);
};
```

#### 5. **System Prompt Support** (Medium Priority)
```cpp
// Add system prompt to all requests
struct InferenceRequest {
    std::string system_prompt;  // NEW
    std::string prompt;
};
```

#### 6. **Metrics Export** (Medium Priority)
```cpp
// Export Prometheus metrics
class MetricsCollector {
    uint64_t total_requests = 0;
    uint64_t total_tokens_generated = 0;
    float avg_latency_ms = 0;
    uint32_t cache_hits = 0;
};
```

#### 7. **Custom Prompt Templates** (Low Priority)
```cpp
// Support Jinja2 or Handlebars templates
struct PromptTemplate {
    std::string template_str;  // "User: {{user_input}}\nAssistant:"
    std::map<std::string, std::string> variables;
    std::string render();
};
```

#### 8. **Context Persistence** (Low Priority)
```cpp
// Keep conversation history in context
class ConversationContext {
    std::deque<std::string> history;
    void add_message(const std::string& role, const std::string& content);
};
```

---

## 🧪 Testing Recommendations

### Critical Path Tests (Must Pass)
- [ ] Model loads without crashing
- [ ] Inference produces non-empty output
- [ ] Multiple requests handled correctly
- [ ] Daemon doesn't crash on bad input
- [ ] Memory stays stable over time
- [ ] Socket connection works reliably

### Edge Case Tests (Should Pass)
- [ ] Very large prompt (10KB+)
- [ ] Very large max_tokens (10000)
- [ ] Rapid-fire requests (100/sec)
- [ ] Queue fills to limit (100 items)
- [ ] Invalid JSON in request
- [ ] Missing required parameters
- [ ] Negative values for max_tokens

### Performance Tests (Target Metrics)
- [ ] Inference latency: < 500ms typical
- [ ] Idle memory: < 50MB
- [ ] Model load: < 30 seconds
- [ ] 100 consecutive requests: all succeed
- [ ] 1-hour stability: no memory growth

---

## 🔍 Code Quality Issues

### Style & Documentation
- [ ] Add Doxygen comments to LlamaWrapper methods
- [ ] Add examples in inline docs
- [ ] Document thread safety assumptions
- [ ] Document error conditions

### Testing Coverage
- [ ] Unit tests for LlamaWrapper::load_model()
- [ ] Unit tests for LlamaWrapper::infer()
- [ ] Unit tests for InferenceQueue
- [ ] Integration tests for full pipeline

### Logging
- [ ] Add debug logs for model load steps
- [ ] Add debug logs for token generation
- [ ] Add metrics logging (requests/sec)
- [ ] Add error codes for each failure mode

---

## 📊 Risk Assessment

| Issue | Severity | Likelihood | Impact | Status |
|-------|----------|------------|--------|--------|
| Input validation | HIGH | HIGH | Crash | 🔴 TODO |
| Inference timeout | HIGH | MEDIUM | Hang | 🔴 TODO |
| Memory leak | HIGH | LOW | OOM | 🟢 OK |
| Config reload | MEDIUM | LOW | Manual restart | 🟡 WORKAROUND |
| Queue limits | MEDIUM | MEDIUM | Silent drop | 🔴 TODO |
| Rate limiting | MEDIUM | LOW | DoS possible | 🟡 NICE-TO-HAVE |
| Error messages | MEDIUM | HIGH | Hard debug | 🟡 IMPROVE |
| Token loop | MEDIUM | LOW | Hang | 🔴 TODO |

---

## ✅ Pre-Production Checklist

Before deploying to production:

- [ ] All HIGH severity issues fixed
- [ ] Input validation added
- [ ] Timeout protection implemented
- [ ] Rate limiting added
- [ ] Error messages improved
- [ ] Documentation updated
- [ ] 24-hour stability test passed
- [ ] Memory profiling completed
- [ ] Security audit done
- [ ] Load testing completed

---

## 📞 Issue Tracking

To formally track these issues:

```bash
# Create GitHub issues with:
# Title: [BUG/ENHANCEMENT] Brief description
# Severity: HIGH/MEDIUM/LOW
# Component: llama_wrapper/inference_queue/etc
# Steps to reproduce: (for bugs)
# Expected: What should happen
# Actual: What actually happens
```

---

## Next Actions

### Immediate (This Week)
1. Run full setup & testing from LLAMA_CPP_SETUP_AND_TESTING.md
2. Document any issues found
3. Fix all HIGH severity bugs

### Short Term (This Sprint)
1. Add input validation
2. Add inference timeout
3. Improve error messages
4. Implement rate limiting

### Long Term (Phase 2)
1. Token streaming
2. Model hot-swap
3. Inference caching
4. Metrics export

---

**Generated**: January 2, 2026
**For**: Cortexd llama.cpp Integration Testing
**Status**: Ready for QA Testing

