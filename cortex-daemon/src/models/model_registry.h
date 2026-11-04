#ifndef MODEL_REGISTRY_H
#define MODEL_REGISTRY_H

#include <string>

namespace cortex {
namespace models {

class ModelRegistry {
public:
    static std::string get_default_model_path();
};

} // namespace models
} // namespace cortex

#endif // MODEL_REGISTRY_H
