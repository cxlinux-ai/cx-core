from cortex.kernel_features.model_lifecycle import ModelConfig


def test_model_config_defaults():
    cfg = ModelConfig("test", "/path/to/model")
    assert cfg.backend == "vllm"
    assert cfg.port == 8000


def test_config_roundtrip():
    cfg = ModelConfig("test", "/model", "llamacpp", 8080)
    data = cfg.to_dict()
    restored = ModelConfig.from_dict(data)
    assert restored.name == cfg.name
    assert restored.backend == cfg.backend
