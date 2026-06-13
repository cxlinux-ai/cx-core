#ifndef LLAMA_ENGINE_H
#define LLAMA_ENGINE_H

#include <string>
#include <vector>
#include <memory>
#include <functional>
#include "llama.h"

namespace cortex {
namespace inference {

class LlamaEngine {
public:
    LlamaEngine();
    ~LlamaEngine();

    bool load_model(const std::string& model_path, int ctx_size = 2048);
    std::string generate(const std::string& prompt, int max_tokens = 512);
    void generate_stream(const std::string& prompt, std::function<void(const std::string&)> callback, int max_tokens = 512);
    void unload_model();

private:
    llama_model* model = nullptr;
    llama_context* ctx = nullptr;
};

} // namespace inference
} // namespace cortex

#endif // LLAMA_ENGINE_H
