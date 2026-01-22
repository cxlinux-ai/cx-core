# Predictive Error Prevention System

The Predictive Error Prevention System in Cortex Linux analyzes installation requests before they are executed to identify potential risks and suggest preventive actions. This system acts as a safety layer to prevent partial or broken installations.

## Features

- **Static Compatibility Checks**: Instant validation of kernel version, RAM, and disk space against package requirements.
- **Historical Failure Analysis**: Automatically detects if a package has failed previously on your specific hardware.
- **AI-Powered Risk Assessment**: Leverage LLMs (Claude, GPT, Ollama) to analyze complex shell commands for underlying risks.
- **Proactive Recommendations**: Provides actionable steps (e.g., "Update kernel first") before a failure occurs.
- **Visual Risk Dashboard**: A color-coded interface built into the CLI for high-visibility warnings.

## How it Works

When you run `cortex install`, the system performs a multi-layer analysis:

1. **System Context**: Detects hardware (CPU, RAM, Storage) and OS (Kernel version).
2. **Command Analysis**: Extracts package names and intent from the planned shell commands.
3. **Multi-Stage Risk Scoring**:
   - **Static**: Rule-based checks (e.g., "Does CUDA work on this kernel?").
   - **Historical**: Database lookup of previous installation attempts.
   - **AI/LLM**: Advanced heuristic analysis (if a provider is configured).

## AI Analysis Deep Dive

The system uses a sophisticated prompting strategy to perform its analysis. Here is exactly how the AI "thinks" through an installation:

1. **Context Injection**: The system sends a detailed "System Snapshot" to the AI, including:
   - Your exact **Kernel Version** and **Distro**.
   - Your available **RAM** and **GPU** models.
   - The **specific shell commands** Cortex plans to run.
   - Any risks already found by our static/historical scanners.

2. **Expert Persona**: The AI is instructed to act as a **Linux System Expert** specializing in error debugging.

3. **Heuristic Check**: The AI evaluates the commands against its training data of known Linux issues (e.g., "Will this specific driver version work with Kernel 6.14?").

4. **Structured Output**: The AI returns a JSON report containing standardized risk levels, human-readable reasons, and actionable recommendations.

This combination of real-time system data and AI reasoning allows Cortex to catch complex failures that simple static rules would miss.

## Example Scenarios

### 1. Incompatible Hardware/Kernel
If you try to install software that requires a specific kernel version (like modern CUDA) on an old system:

```text
ℹ️  Potential issues detected: Low Risk

Low Risk:
   - CUDA installation detected on kernel 6.14.0-35-generic.

Recommendation:
   1. Ensure official NVIDIA drivers are installed before proceeding
```

### 2. High-Risk Repeated Failure
If a package has failed multiple times, the system escalates the risk level:

```text
⚠️  Potential issues detected:

High Risk:
   - This software (or related components) failed 3 times in previous attempts.

Recommendation:
   1. Check system logs for dependency conflicts.
   2. Verify package name is correct for your distribution.

Predicted Error Messages:
   ! E: Package 'nvidia-384' has no installation candidate
```

## AI Usage Statement

This feature was developed with heavy assistance from the **Antigravity AI (Google DeepMind)**.
- **Generated Logic**: The core `PredictiveErrorManager` logic and history pattern matching were AI-suggested.
- **Test Generation**: Unit tests were designed using AI to reach 87% coverage.
- **Documentation**: This documentation was refined by the AI to match the final implementation style.

## Testing

To verify the system manually:
1. Ensure you have the project environment setup: `pip install -e .`
2. Run unit tests: `pytest tests/unit/test_predictive_prevention.py`
3. **Verify with Real AI**:
   This tests the full pipeline including LLM-based risk assessment.
   ```bash
   # 1. Ensure your API key is set
   export ANTHROPIC_API_KEY=sk-ant-...

   # 2. Run an installation that might trigger warnings (e.g., CUDA on non-NVIDIA system)
   cortex install "cuda-toolkit" --dry-run
   ```

## Development

Developers can add new static rules in `cortex/predictive_prevention.py` within the `_check_static_compatibility` method.
