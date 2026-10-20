#include "model_registry.h"

#include <cstdlib>

namespace cortex {
namespace models {

std::string ModelRegistry::get_default_model_path() {
    if (const char* env_p = std::getenv("CORTEX_MODEL_PATH")) {
        return std::string(env_p);
    }
#ifdef _WIN32
    if (const char* env_pd = std::getenv("ProgramData")) {
        return std::string(env_pd) + "\\cortex\\models\\default.gguf";
    }
    return "C:\\ProgramData\\cortex\\models\\default.gguf";
#else
    return "/var/lib/cortex/models/default.gguf";
#endif
}

} // namespace models
} // namespace cortex
