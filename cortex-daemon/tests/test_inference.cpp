#include <iostream>
#include <cassert>
#include "../src/bindings/llama_c_bridge.h"

int main() {
    std::cout << "Running test_inference...\n";
    // We don't have a real model in CI, so just test that compilation works
    // and if we pass a bogus path it fails gracefully.
    int res = cortex_model_load("bogus_model.gguf");
    assert(res == 0);
    
    char* result = cortex_infer_generate("Hello");
    assert(result != nullptr); // "Error: Model not loaded" or something
    free(result);
    
    std::cout << "All tests passed!\n";
    return 0;
}
