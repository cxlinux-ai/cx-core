# LLM Router for Cortex Linux

## Overview

The LLM Router intelligently routes requests to the most appropriate AI model based on task type, providing optimal performance and cost efficiency for Cortex Linux operations.

## Why Multi-LLM Architecture?

**Different tasks require different strengths:**
- **Claude Sonnet 4:** Best for natural language understanding, user interaction, requirement parsing
- **Kimi K2:** Superior for system operations (65.8% SWE-bench), debugging, tool use, agentic tasks

**Business Benefits:**
- 🎯 **Performance:** Use best-in-class model for each task type
- 💰 **Cost Savings:** Kimi K2 estimated 40-50% cheaper than Claude for system operations
- 🔒 **Flexibility:** Open weights (Kimi K2) enables self-hosting for enterprise
- 🚀 **Competitive Edge:** "LLM-agnostic OS" differentiates from single-model competitors

## Architecture

```
User Request
    ↓
[LLM Router]
    ├─→ Claude API (chat, requirements)
    └─→ Kimi K2 API (system ops, debugging)
    ↓
Response + Metadata (cost, tokens, latency)
```

### Routing Logic

| Task Type | Routed To | Reasoning |
|-----------|-----------|-----------|
| User Chat | Claude | Better natural language |
| Requirement Parsing | Claude | Understanding user intent |
| System Operations | Kimi K2 | 65.8% SWE-bench (vs Claude's 50.2%) |
| Error Debugging | Kimi K2 | Superior technical problem-solving |
| Code Generation | Kimi K2 | 53.7% LiveCodeBench (vs 48.5%) |
| Dependency Resolution | Kimi K2 | Better at complex logic |
| Configuration | Kimi K2 | System-level expertise |
| Tool Execution | Kimi K2 | 65.8% on Tau2 Telecom (vs 45.2%) |

## Installation

### Prerequisites

```bash
pip install anthropic openai
```

### API Keys

Set environment variables:

```bash
export ANTHROPIC_API_KEY="your-claude-key"
export MOONSHOT_API_KEY="your-kimi-key"
```

Or pass directly to `LLMRouter()`:

```python
from llm_router import LLMRouter

router = LLMRouter(
    claude_api_key="your-claude-key",
    kimi_api_key="your-kimi-key"
)
```

## Usage

### Basic Example

```python
from llm_router import LLMRouter, TaskType

router = LLMRouter()

# User chat (automatically routed to Claude)
response = router.complete(
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello! What can you help me with?"}
    ],
    task_type=TaskType.USER_CHAT
)

print(f"Provider: {response.provider.value}")
print(f"Response: {response.content}")
print(f"Cost: ${response.cost_usd:.6f}")
```

### System Operation Example

```python
# System operations automatically routed to Kimi K2
response = router.complete(
    messages=[
        {"role": "system", "content": "You are a Linux system administrator."},
        {"role": "user", "content": "Install CUDA drivers for NVIDIA RTX 4090"}
    ],
    task_type=TaskType.SYSTEM_OPERATION
)

print(f"Provider: {response.provider.value}")  # kimi_k2
print(f"Instructions: {response.content}")
```

### Convenience Function

For simple one-off requests:

```python
from llm_router import complete_task, TaskType

response = complete_task(
    prompt="Diagnose why apt install failed with dependency errors",
    task_type=TaskType.ERROR_DEBUGGING,
    system_prompt="You are a Linux troubleshooting expert"
)

print(response)
```

## Advanced Features

### Force Specific Provider

Override routing logic when needed:

```python
from llm_router import LLMProvider

# Force Claude even for system operations
response = router.complete(
    messages=[{"role": "user", "content": "Install PostgreSQL"}],
    task_type=TaskType.SYSTEM_OPERATION,
    force_provider=LLMProvider.CLAUDE
)
```

### Fallback Behavior

Router automatically falls back to alternate provider if primary fails:

```python
router = LLMRouter(
    claude_api_key="valid-key",
    kimi_api_key="invalid-key",  # Will fail
    enable_fallback=True  # Automatically try Claude
)

# System op would normally use Kimi, but will fallback to Claude
response = router.complete(
    messages=[{"role": "user", "content": "Install CUDA"}],
    task_type=TaskType.SYSTEM_OPERATION
)
# Returns Claude response instead of failing
```

### Cost Tracking

Track usage and costs across providers:

```python
router = LLMRouter(track_costs=True)

# Make several requests...
response1 = router.complete(...)
response2 = router.complete(...)

# Get statistics
stats = router.get_stats()
print(f"Total requests: {stats['total_requests']}")
print(f"Total cost: ${stats['total_cost_usd']}")
print(f"Claude requests: {stats['providers']['claude']['requests']}")
print(f"Kimi K2 requests: {stats['providers']['kimi_k2']['requests']}")

# Reset for new session
router.reset_stats()
```

### Tool Calling

Both providers support tool calling:

```python
tools = [{
    "type": "function",
    "function": {
        "name": "execute_bash",
        "description": "Execute bash command in sandbox",
        "parameters": {
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Bash command to execute"
                }
            }
        }
    }
}]

response = router.complete(
    messages=[{"role": "user", "content": "Install git"}],
    task_type=TaskType.SYSTEM_OPERATION,
    tools=tools
)

# Model will autonomously decide when to call tools
```

## Integration with Cortex Linux

### Package Manager Wrapper

```python
from llm_router import LLMRouter, TaskType

class PackageManagerWrapper:
    def __init__(self):
        self.router = LLMRouter()
    
    def install(self, package_description: str):
        """Install package based on natural language description."""
        response = self.router.complete(
            messages=[
                {"role": "system", "content": "You are a package manager expert."},
                {"role": "user", "content": f"Install: {package_description}"}
            ],
            task_type=TaskType.SYSTEM_OPERATION
        )
        
        # Kimi K2 will handle this with superior agentic capabilities
        return response.content
```

### Error Diagnosis

```python
def diagnose_error(error_message: str, command: str):
    """Diagnose installation errors and suggest fixes."""
    router = LLMRouter()
    
    response = router.complete(
        messages=[
            {"role": "system", "content": "You are a Linux troubleshooting expert."},
            {"role": "user", "content": f"Command: {command}\nError: {error_message}\nWhat went wrong and how to fix?"}
        ],
        task_type=TaskType.ERROR_DEBUGGING
    )
    
    # Kimi K2's superior debugging capabilities
    return response.content
```

### User Interface Chat

```python
def chat_with_user(user_message: str):
    """Handle user-facing chat interactions."""
    router = LLMRouter()
    
    response = router.complete(
        messages=[
            {"role": "system", "content": "You are Cortex, a friendly AI assistant."},
            {"role": "user", "content": user_message}
        ],
        task_type=TaskType.USER_CHAT
    )
    
    # Claude's superior natural language understanding
    return response.content
```

## Configuration

### Default Settings

```python
router = LLMRouter(
    claude_api_key=None,              # Reads from ANTHROPIC_API_KEY
    kimi_api_key=None,                # Reads from MOONSHOT_API_KEY
    default_provider=LLMProvider.CLAUDE,  # Fallback if routing fails
    enable_fallback=True,             # Try alternate if primary fails
    track_costs=True                  # Track usage statistics
)
```

### Custom Routing Rules

Override default routing logic:

```python
from llm_router import LLMRouter, TaskType, LLMProvider

router = LLMRouter()

# Override routing rules
router.ROUTING_RULES[TaskType.CODE_GENERATION] = LLMProvider.CLAUDE

# Now code generation uses Claude instead of Kimi K2
```

## Performance Benchmarks

### Task-Specific Performance

| Benchmark | Kimi K2 | Claude Sonnet 4 | Advantage |
|-----------|---------|-----------------|-----------|
| SWE-bench Verified (Agentic) | 65.8% | 50.2% | +31% Kimi K2 |
| LiveCodeBench | 53.7% | 48.5% | +11% Kimi K2 |
| Tau2 Telecom (Tool Use) | 65.8% | 45.2% | +45% Kimi K2 |
| TerminalBench | 25.0% | - | Kimi K2 only |
| MMLU (General Knowledge) | 89.5% | 91.5% | +2% Claude |
| SimpleQA | 31.0% | 15.9% | +95% Kimi K2 |

**Key Insight:** Kimi K2 excels at system operations, debugging, and agentic tasks. Claude better for general chat.

### Cost Comparison (Estimated)

Assuming 1,000 system operations per day:

| Scenario | Cost/Month | Savings |
|----------|------------|---------|
| Claude Only | $3,000 | Baseline |
| Hybrid (70% Kimi K2) | $1,500 | 50% |
| Kimi K2 Only | $1,200 | 60% |

**Real savings depend on actual task distribution and usage patterns.**

## Testing

### Run All Tests

```bash
cd /path/to/issue-34
python3 test_llm_router.py
```

### Test Coverage

- ✅ Routing logic for all task types
- ✅ Fallback behavior when provider unavailable
- ✅ Cost calculation and tracking
- ✅ Claude API integration
- ✅ Kimi K2 API integration
- ✅ Tool calling support
- ✅ Error handling
- ✅ End-to-end scenarios

### Example Test Output

```
test_claude_completion ... ok
test_cost_calculation_claude ... ok
test_fallback_on_error ... ok
test_kimi_completion ... ok
test_routing_user_chat_to_claude ... ok
test_routing_system_op_to_kimi ... ok
test_stats_tracking ... ok

----------------------------------------------------------------------
Ran 35 tests in 0.523s

OK
```

## Troubleshooting

### Issue: "RuntimeError: Claude API not configured"

**Solution:** Set ANTHROPIC_API_KEY environment variable or pass `claude_api_key` to constructor.

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

### Issue: "RuntimeError: Kimi K2 API not configured"

**Solution:** Get API key from https://platform.moonshot.ai and set MOONSHOT_API_KEY.

```bash
export MOONSHOT_API_KEY="your-key-here"
```

### Issue: High costs

**Solution:** Enable cost tracking to identify expensive operations:

```python
router = LLMRouter(track_costs=True)
# ... make requests ...
stats = router.get_stats()
print(f"Total cost: ${stats['total_cost_usd']}")
```

Consider:
- Using Kimi K2 more (cheaper)
- Reducing max_tokens
- Caching common responses

### Issue: Slow responses

Check latency per provider:

```python
response = router.complete(...)
print(f"Latency: {response.latency_seconds:.2f}s")
```

Consider:
- Parallel requests for batch operations
- Lower max_tokens for faster responses
- Self-hosting Kimi K2 for lower latency

## Deployment Options

### Option 1: Cloud APIs (Recommended for Seed Stage)

**Pros:**
- ✅ Zero infrastructure cost
- ✅ Fast deployment (hours)
- ✅ Scales automatically
- ✅ Latest model versions

**Cons:**
- ❌ Per-token costs
- ❌ API rate limits
- ❌ Data leaves premises

**Cost:** ~$1,500-3,000/month for 10K users

### Option 2: Self-Hosted Kimi K2 (Post-Seed)

**Pros:**
- ✅ Lower long-term costs
- ✅ No API limits
- ✅ Full control
- ✅ Data privacy

**Cons:**
- ❌ High upfront cost (4x A100 GPUs = $50K+)
- ❌ Maintenance overhead
- ❌ DevOps complexity

**Cost:** $1,000-2,000/month (GPU + power + ops)

### Option 3: Hybrid (Recommended for Series A)

Use cloud for spikes, self-hosted for baseline:

- Claude API: User-facing chat
- Self-hosted Kimi K2: System operations (high volume)
- Fallback to APIs if self-hosted overloaded

**Best of both worlds.**

## Business Value

### For Seed Round Pitch

**Technical Differentiation:**
- "Multi-LLM architecture shows technical sophistication"
- "Best-in-class model for each task type"
- "65.8% SWE-bench score beats most proprietary models"

**Cost Story:**
- "40-50% lower AI costs than single-model competitors"
- "Estimated savings: $18K-36K/year per 10K users"

**Enterprise Appeal:**
- "Open weights (Kimi K2) = self-hostable"
- "Data never leaves customer infrastructure"
- "LLM-agnostic = no vendor lock-in"

### Competitive Analysis

| Competitor | LLM Strategy | Cortex Advantage |
|------------|--------------|------------------|
| Cursor | VS Code + Claude | Wraps editor only |
| GitHub Copilot | GitHub + GPT-4 | Code only |
| Replit | IDE + GPT | Not OS-level |
| **Cortex Linux** | **Multi-LLM OS** | **Entire system** |

**Cortex is the only AI-native operating system with intelligent LLM routing.**

## Roadmap

### Phase 1 (Current): Dual-LLM Support
- ✅ Claude + Kimi K2 integration
- ✅ Intelligent routing
- ✅ Cost tracking
- ✅ Fallback logic

### Phase 2 (Q1 2026): Multi-Provider
- ⬜ Add DeepSeek-V3 support
- ⬜ Add Qwen3 support
- ⬜ Add Llama 4 support
- ⬜ User-configurable provider preferences

### Phase 3 (Q2 2026): Self-Hosting
- ⬜ Self-hosted Kimi K2 deployment guide
- ⬜ vLLM integration
- ⬜ SGLang integration
- ⬜ Load balancing between cloud + self-hosted

### Phase 4 (Q3 2026): Advanced Routing
- ⬜ ML-based routing (learn from outcomes)
- ⬜ Cost-optimized routing
- ⬜ Latency-optimized routing
- ⬜ Quality-optimized routing

## Contributing

We welcome contributions! Areas of interest:

1. **Additional LLM Support:** DeepSeek-V3, Qwen3, Llama 4
2. **Self-Hosting Guides:** vLLM, SGLang, TensorRT-LLM deployment
3. **Performance Benchmarks:** Real-world Cortex Linux task benchmarks
4. **Cost Optimization:** Smarter routing algorithms

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.

## License

Modified MIT License - see [LICENSE](../LICENSE) for details.

## Support

- **GitHub Issues:** https://github.com/cortexlinux/cortex/issues
- **Discord:** https://discord.gg/uCqHvxjU83
- **Email:** mike@cortexlinux.com

## References

- [Kimi K2 Technical Report](https://arxiv.org/abs/2507.20534)
- [Anthropic Claude Documentation](https://docs.anthropic.com)
- [Moonshot AI Platform](https://platform.moonshot.ai)
- [SWE-bench Leaderboard](https://www.swebench.com)

---

**Built with ❤️ by the Cortex Linux Team**
