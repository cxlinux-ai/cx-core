#include "llama_c_bridge.h"
#include "../inference/inference_manager.h"
#include <string.h>
#include <stdlib.h>

extern "C" {

int cortex_model_load(const char* model_path) {
    if (!model_path) return 0;
    bool success = cortex::inference::InferenceManager::get_instance().load_model(std::string(model_path));
    return success ? 1 : 0;
}

char* cortex_infer_generate(const char* prompt) {
    if (!prompt) return nullptr;
    std::string result = cortex::inference::InferenceManager::get_instance().generate_text(std::string(prompt));
    
#ifdef _WIN32
    return _strdup(result.c_str());
#else
    return strdup(result.c_str());
#endif
}

int cortex_infer_generate_stream(const char* prompt, cortex_stream_callback callback, void* user_data) {
    if (!prompt || !callback) return 0;
    
    cortex::inference::InferenceManager::get_instance().generate_stream(std::string(prompt), [callback, user_data](const std::string& chunk) {
        callback(chunk.c_str(), user_data);
    });
    
    return 1;
}

}
