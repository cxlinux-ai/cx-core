# Default local model download source (unchanged)

The default GGUF model for `cx ai download` / offline `cx ask --local` is pulled from Hugging Face:

| Constant | Value | File |
|----------|--------|------|
| `HF_REPO` | `ShreemJ/cxlinux-ai-7b` | `wezterm/src/cli/model_utils.rs` |
| `MODEL_FILENAME` | `cxlinux-ai-7b-Q4_K_M.gguf` | `wezterm/src/cli/model_utils.rs` |

Download implementation: `wezterm/src/cli/ai.rs` (`hf_hub::api::tokio::Api`, `repo.get(MODEL_FILENAME)`).

This document is informational only; the repo URL is not modified by safety work.
