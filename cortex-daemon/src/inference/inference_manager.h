#ifndef INFERENCE_MANAGER_H
#define INFERENCE_MANAGER_H

#include <string>
#include <memory>
#include <functional>
#include "llama_engine.h"

namespace cortex {
namespace inference {

class InferenceManager {
public:
    static InferenceManager& get_instance() {
        static InferenceManager instance;
        return instance;
    }
    
    bool load_model(const std::string& model_path);
    std::string generate_text(const std::string& prompt);
    void generate_stream(const std::string& prompt, std::function<void(const std::string&)> callback);

private:
    InferenceManager() = default;
    std::unique_ptr<LlamaEngine> engine;
};

} // namespace inference
} // namespace cortex

#endif // INFERENCE_MANAGER_H
