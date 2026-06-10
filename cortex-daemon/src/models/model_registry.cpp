#include "model_registry.h"

namespace cortex {
namespace models {

std::string ModelRegistry::get_default_model_path() {
    return "/var/lib/cortex/models/default.gguf";
}

} // namespace models
} // namespace cortex
