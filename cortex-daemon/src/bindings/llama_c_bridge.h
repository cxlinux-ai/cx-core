#ifndef LLAMA_C_BRIDGE_H
#define LLAMA_C_BRIDGE_H

#ifdef __cplusplus
extern "C" {
#endif

// Initialize the engine and load a model
int cortex_model_load(const char* model_path);

// Generate text and return a newly allocated string. Caller must free().
char* cortex_infer_generate(const char* prompt);

// Streaming support
typedef void (*cortex_stream_callback)(const char* token, void* user_data);
int cortex_infer_generate_stream(const char* prompt, cortex_stream_callback callback, void* user_data);

#ifdef __cplusplus
}
#endif

#endif // LLAMA_C_BRIDGE_H
