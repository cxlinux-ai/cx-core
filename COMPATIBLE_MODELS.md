# Cortex Daemon - Compatible LLM Models

## ✅ Supported Models

Any GGUF format model works with Cortex Daemon. Here are popular options:

### **Small Models (Fast, Low Memory)**
- **TinyLlama 1.1B** (~600MB) - Currently loaded
  ```
  tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
  ```
  - Fastest inference
  - Best for testing/development
  - Runs on minimal hardware

- **Phi 2.7B** (~1.6GB)
  ```
  phi-2.Q4_K_M.gguf
  ```
  - Good balance of speed and quality
  - Strong performance on reasoning tasks

- **Qwen 1.8B** (~1GB)
  ```
  qwen1_5-1_8b-chat-q4_k_m.gguf
  ```
  - Multilingual support
  - Fast inference

### **Medium Models (Balanced)**
- **Mistral 7B** (~4GB)
  ```
  mistral-7b-instruct-v0.2.Q4_K_M.gguf
  ```
  - Good quality responses
  - Reasonable inference time
  - Most popular choice

- **Llama 2 7B** (~4GB)
  ```
  llama-2-7b-chat.Q4_K_M.gguf
  ```
  - Strong base model
  - Good instruction following

- **Neural Chat 7B** (~4GB)
  ```
  neural-chat-7b-v3-1.Q4_K_M.gguf
  ```
  - Optimized for conversation
  - Better context understanding

### **Large Models (High Quality)**
- **Mistral 8x7B** (~26GB - Mixture of Experts)
  ```
  mistral-8x7b-instruct-v0.1.Q3_K_M.gguf
  ```
  - Very capable
  - Requires more resources

- **Llama 2 13B** (~8GB)
  ```
  llama-2-13b-chat.Q4_K_M.gguf
  ```
  - Higher quality than 7B
  - Slower inference

### **Specialized Models**
- **Code Llama 7B** (~4GB)
  ```
  codellama-7b-instruct.Q4_K_M.gguf
  ```
  - Optimized for code generation
  - Strong programming knowledge

- **WizardCoder 7B** (~4GB)
  ```
  wizardcoder-7b.Q4_K_M.gguf
  ```
  - Excellent for coding tasks
  - Based on Code Llama

- **Orca 2 7B** (~4GB)
  ```
  orca-2-7b.Q4_K_M.gguf
  ```
  - Strong reasoning capabilities
  - Good at complex tasks

## 🔄 How to Switch Models

1. **Download a new model:**
   ```bash
   cd ~/.cortex/models
   wget https://huggingface.co/TheBloke/[MODEL-NAME]-GGUF/resolve/main/[MODEL-FILE].gguf
   ```

2. **Update config:**
   ```bash
   sudo nano /etc/cortex/daemon.conf
   ```
   Change the `model_path` line to point to new model

3. **Restart daemon:**
   ```bash
   sudo systemctl restart cortexd
   ```

4. **Verify:**
   ```bash
   cortex daemon health  # Should show LLM Loaded: Yes
   sudo journalctl -u cortexd -n 20 | grep "Model loaded"
   ```

## 📊 Model Comparison

| Model | Size | Memory | Speed | Quality | Use Case |
|-------|------|--------|-------|---------|----------|
| TinyLlama 1.1B | 600MB | <1GB | ⚡⚡⚡⚡⚡ | ⭐⭐ | Testing, Learning |
| Phi 2.7B | 1.6GB | 2-3GB | ⚡⚡⚡⚡ | ⭐⭐⭐ | Development |
| Mistral 7B | 4GB | 5-6GB | ⚡⚡⚡ | ⭐⭐⭐⭐ | Production |
| Llama 2 13B | 8GB | 9-10GB | ⚡⚡ | ⭐⭐⭐⭐⭐ | High Quality |
| Mistral 8x7B | 26GB | 28-30GB | ⚡ | ⭐⭐⭐⭐⭐ | Expert Tasks |

## 🔍 Finding More Models

Visit: https://huggingface.co/TheBloke

TheBloke has converted 1000+ models to GGUF format. All are compatible with Cortex!

## ⚙️ Configuration Tips

### For Fast Inference (Testing):
```
model_path: ~/.cortex/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
memory_limit_mb: 50
max_inference_queue_size: 50
```

### For Balanced (Default):
```
model_path: ~/.cortex/models/mistral-7b-instruct-v0.2.Q4_K_M.gguf
memory_limit_mb: 150
max_inference_queue_size: 100
```

### For High Quality:
```
model_path: ~/.cortex/models/llama-2-13b-chat.Q4_K_M.gguf
memory_limit_mb: 256
max_inference_queue_size: 50
```

## ❓ Quantization Explained

- **Q4_K_M**: Best balance (Recommended) - ~50% of original size
- **Q5_K_M**: Higher quality - ~75% of original size  
- **Q6_K**: Near-original quality - ~90% of original size
- **Q3_K_M**: Smaller size - ~35% of original size (faster but lower quality)

Lower number = faster but less accurate
Higher number = slower but higher quality

## 🧪 Test Compatibility

To test if a model works:
```bash
# Download model
wget https://huggingface.co/[...]/model.gguf -O ~/.cortex/models/test.gguf

# Update config to point to test.gguf
# Restart daemon
sudo systemctl restart cortexd

# Check if loaded
cortex daemon health
```

If "LLM Loaded: Yes", it's compatible! ✅
