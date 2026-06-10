#include "inference_manager.h"

namespace cortex {
namespace inference {

bool InferenceManager::load_model(const std::string& model_path) {
    if (!engine) {
        engine = std::make_unique<LlamaEngine>();
    }
    return engine->load_model(model_path);
}

std::string InferenceManager::generate_text(const std::string& prompt) {
    if (!engine) {
        return "Error: Engine not initialized.";
    }
    return engine->generate(prompt);
}

void InferenceManager::generate_stream(const std::string& prompt, std::function<void(const std::string&)> callback) {
    if (!engine) {
        callback("Error: Engine not initialized.");
        return;
    }
    engine->generate_stream(prompt, callback);
}

} // namespace inference
} // namespace cortex
