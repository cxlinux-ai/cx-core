#include "llama_engine.h"
#include <iostream>
#include <stdexcept>
#include <cstring>

namespace cortex {
namespace inference {

LlamaEngine::LlamaEngine() {
    llama_backend_init();
}

LlamaEngine::~LlamaEngine() {
    unload_model();
    llama_backend_free();
}

bool LlamaEngine::load_model(const std::string& model_path, int ctx_size) {
    unload_model();
    
    llama_model_params mparams = llama_model_default_params();
    model = llama_model_load_from_file(model_path.c_str(), mparams);
    if (!model) {
        std::cerr << "Failed to load model from " << model_path << "\n";
        return false;
    }
    
    llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx = ctx_size > 0 ? ctx_size : 2048;
    
    ctx = llama_init_from_model(model, cparams);
    if (!ctx) {
        std::cerr << "Failed to create context\n";
        unload_model();
        return false;
    }
    return true;
}

void LlamaEngine::unload_model() {
    if (ctx) {
        llama_free(ctx);
        ctx = nullptr;
    }
    if (model) {
        llama_model_free(model);
        model = nullptr;
    }
}

static void common_batch_add(llama_batch & batch, llama_token id, llama_pos pos, const std::vector<llama_seq_id> & seq_ids, bool logits) {
    batch.token   [batch.n_tokens] = id;
    batch.pos     [batch.n_tokens] = pos;
    batch.n_seq_id[batch.n_tokens] = seq_ids.size();
    for (size_t i = 0; i < seq_ids.size(); ++i) {
        batch.seq_id[batch.n_tokens][i] = seq_ids[i];
    }
    batch.logits  [batch.n_tokens] = logits;
    batch.n_tokens++;
}

static void common_batch_clear(llama_batch & batch) {
    batch.n_tokens = 0;
}

void LlamaEngine::generate_stream(const std::string& prompt, std::function<void(const std::string&)> callback, int max_tokens) {
    if (!ctx) {
        callback("Error: Model not loaded");
        return;
    }
    
    const llama_vocab* vocab = llama_model_get_vocab(model);
    
    // Convert prompt to tokens
    std::vector<llama_token> tokens_list(prompt.size() + 2, 0);
    int n_tokens = llama_tokenize(vocab, prompt.c_str(), prompt.length(), tokens_list.data(), tokens_list.size(), true, false);
    
    if (n_tokens < 0) {
        tokens_list.resize(-n_tokens);
        n_tokens = llama_tokenize(vocab, prompt.c_str(), prompt.length(), tokens_list.data(), tokens_list.size(), true, false);
    }
    tokens_list.resize(n_tokens);
    
    // Evaluate initial prompt
    llama_batch batch = llama_batch_init(n_tokens, 0, 1);
    for (size_t i = 0; i < tokens_list.size(); i++) {
        common_batch_add(batch, tokens_list[i], i, {0}, false);
    }
    batch.logits[batch.n_tokens - 1] = true;
    
    if (llama_decode(ctx, batch) != 0) {
        llama_batch_free(batch);
        callback("Error decoding prompt");
        return;
    }
    
    int n_cur = batch.n_tokens;
    int n_vocab = llama_vocab_n_tokens(vocab);
    
    // Generate
    while (n_cur < max_tokens + (int)tokens_list.size()) {
        struct llama_sampler* smpl = llama_sampler_init_greedy();
        llama_token new_token_id = llama_sampler_sample(smpl, ctx, -1);
        llama_sampler_free(smpl);
        
        if (llama_vocab_is_eog(vocab, new_token_id)) {
            break;
        }
        
        // Convert token to string
        char buf[128];
        int n_chars = llama_token_to_piece(vocab, new_token_id, buf, sizeof(buf), 0, true);
        if (n_chars > 0) {
            callback(std::string(buf, n_chars));
        }
        
        common_batch_clear(batch);
        common_batch_add(batch, new_token_id, n_cur, {0}, true);
        
        if (llama_decode(ctx, batch) != 0) {
            break;
        }
        n_cur++;
    }
    
    llama_batch_free(batch);
}

std::string LlamaEngine::generate(const std::string& prompt, int max_tokens) {
    std::string full_response;
    generate_stream(prompt, [&](const std::string& chunk) {
        full_response += chunk;
    }, max_tokens);
    return full_response;
}

} // namespace inference
} // namespace cortex
