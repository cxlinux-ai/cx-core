#include <iostream>
#include <string>
#include <cstdlib>
#include "bindings/llama_c_bridge.h"
#include "models/model_registry.h"

int main(int argc, char** argv) {
    std::cout << "Starting cortex-daemon...\n";
    
    std::string model_path = cortex::models::ModelRegistry::get_default_model_path();
    if (argc > 1) {
        model_path = argv[1];
    }
    
    std::cout << "Loading model: " << model_path << "\n";
    if (!cortex_model_load(model_path.c_str())) {
        std::cerr << "Failed to load model.\n";
        return 1;
    }
    
    std::string prompt;
    std::cout << "> ";
    while (std::getline(std::cin, prompt)) {
        if (prompt.empty()) {
            std::cout << "> ";
            continue;
        }
        
        char* response = cortex_infer_generate(prompt.c_str());
        if (response) {
            std::cout << response << "\n";
            free(response);
        } else {
            std::cerr << "Inference failed.\n";
        }
        std::cout << "> ";
    }
    
    return 0;
}
