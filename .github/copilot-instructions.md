# GitHub Copilot Instructions for CX Linux

## Project Overview
CX Linux is the AI-native OS layer for the $50B Linux system administration market. Instead of memorizing commands and googling errors, users describe their intent and the AI executes it safely and intelligently.

## What Copilot is Best At Working On

### 🎯 High-Value Areas for AI Assistance

GitHub Copilot excels at helping with these CX Terminal components:

#### 1. **AI Agent Development** ⭐⭐⭐
- **Why:** Repetitive patterns with agent trait implementations
- **Tasks:** Adding new specialized agents (cloud providers, package managers, system introspection)
- **Pattern:** `impl Agent for NewAgent { async fn execute() { ... } }`
- **Impact:** Each new agent multiplies platform capabilities

#### 2. **Voice/Audio Pipeline** ⭐⭐⭐
- **Why:** Complex audio processing with standard patterns
- **Tasks:** Speech transcription, audio buffering, voice command mapping to CLI
- **Components:** `voice/` module with cpal audio capture
- **Pattern:** Async audio stream processing, VAD (Voice Activity Detection)

#### 3. **Learning/ML Components** ⭐⭐⭐
- **Why:** Local intent understanding and ranking over history amplify LLM effectiveness
- **Tasks:** Command suggestion ranking, retrieval over command/history logs, lightweight scoring heuristics
- **Components:** `cx/llm/` routing plus local history/telemetry store for privacy-preserving behavior learning (future advanced ML optional)
- **Pattern:** LLM-guided retrieval and statistical signals over local command history without external data

#### 4. **Rendering & UI Logic** ⭐⭐
- **Why:** Complex layout math and WebGPU shader boilerplate
- **Tasks:** Text painting algorithms, glyph caching, tab bar layouts, WGSL shaders
- **Components:** `render/` and `termwindow/` modules
- **Caution:** Performance-critical; suggest benchmarks

#### 5. **Protocol/IPC Layer** ⭐⭐
- **Why:** JSON-RPC serialization patterns are mechanical
- **Tasks:** Message types, daemon communication, Unix socket handling
- **Components:** `cx_daemon/` module with 4-byte length-prefixed JSON-RPC
- **Pattern:** Serde serialization with proper error handling

#### 6. **Test Coverage** ⭐⭐⭐
- **Why:** Test boilerplate is highly repetitive
- **Tasks:** Unit tests, integration tests, mock implementations, error scenarios
- **Target:** 95%+ coverage on new code
- **Pattern:** Tokio async tests with proper cleanup

#### 7. **CLI Command Implementation** ⭐⭐
- **Why:** Clap argument parsing follows predictable patterns
- **Tasks:** Adding new `cx` subcommands with help text and validation
- **Components:** CLI modules for user-facing commands
- **Pattern:** Natural language intent parsing with safety validation

### ⚠️ Areas Requiring Caution

Copilot should be more conservative in these areas:

#### Security-Critical Code ❌
- Command validation and sandboxing logic
- Privilege escalation prevention
- Authentication/authorization flows (subscription, license validation)
- **Approach:** Manual review required; suggest defensive patterns

#### Core Terminal Emulation 🔶
- VT/ANSI escape sequence parsing (inherited from WezTerm)
- PTY handling and process management
- **Approach:** These are mature; avoid unnecessary changes

#### Cryptographic Operations ❌
- SSH key handling, certificate validation
- Encryption/decryption routines
- **Approach:** Only suggest well-vetted libraries (ring, rustls)

### 💡 Optimal Copilot Usage Patterns

**Best practices when using Copilot on this codebase:**

1. **New Agent Scaffolding:** Copilot can generate entire agent implementations from trait signatures
2. **Lua Binding Boilerplate:** Let Copilot write FFI bindings after you define the Rust signature
3. **Test Generation:** Provide function signature + expected behavior, get comprehensive tests
4. **Error Handling:** Copilot excels at adding `anyhow::Result` error propagation
5. **Async Patterns:** Trust Copilot for Tokio async/await boilerplate
6. **Documentation:** Effective at generating rustdoc comments from function signatures
7. **Refactoring:** Good at mechanical refactors (rename, extract function, update imports)

**When to ignore Copilot suggestions:**

- Security-critical validation logic (always manually review)
- Performance-critical hot paths (profile before accepting)
- Architecture decisions (require human judgment)
- Breaking changes to public APIs (consider compatibility)

## MANDATORY PRIORITIES

### 1. BSL 1.1 License Protection ⚠️
- ALL code suggestions must include BSL 1.1 license header
- NEVER suggest Apache, MIT, or other permissive licenses
- Business Source License protects competitive advantage for 4 years
- Owned by AI Venture Holdings LLC

```python
"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
"""
```

### 2. Zero Documentation OS Layer
- Suggest self-documenting natural language interfaces
- Intent-driven patterns: `cx "install web server"` not `apt install nginx`
- Comments explain WHY, never WHAT or HOW
- Progressive capability discovery through usage
- No user manuals - the AI IS the interface

### 3. Founding 1,000 Network Effects
- Every feature suggestion must strengthen community lock-in
- Include referral tracking in user-facing components
- Suggest founding member exclusive capabilities
- 10% lifetime revenue sharing for referrals

### 4. Enterprise Rust/Python Architecture
- Python 3.11+: asyncio, Pydantic v2, proper typing
- Rust: Tokio, Serde, clap, anyhow error handling
- 95%+ test coverage suggestions
- Sandboxed execution patterns
- Structured logging and metrics

## Code Standards

### ✅ Suggest These Patterns:

```python
# Enterprise async patterns with security
from cx.security import CommandValidator
from cx.types import SafeCommand, ExecutionResult

async def execute_user_intent(intent: str) -> ExecutionResult:
    """Natural language intent execution with safety validation."""
    try:
        safe_cmd = await CommandValidator.parse_intent(intent)
        result = await safe_cmd.execute_sandboxed()
        await audit_logger.log_execution(intent, safe_cmd, result)
        return result
    except SecurityViolation as e:
        raise CommandRejectedError(f"Unsafe command rejected: {e}")
```

```python
# Founding member referral tracking
@dataclass
class UserOnboarding:
    referral_code: str = Field(factory=generate_referral_code)
    referred_by: Optional[str] = None
    founding_member: bool = False

    async def process_referral_signup(self, referrer_code: str) -> ReferralResult:
        """Process new user signup with referral tracking."""
```

```rust
// Rust performance-critical components
use tokio::process::Command;
use serde::{Deserialize, Serialize};
use anyhow::Result;

#[derive(Serialize, Deserialize)]
pub struct SafeCommand {
    intent: String,
    validated_cmd: Vec<String>,
    risk_level: RiskLevel,
}

impl SafeCommand {
    pub async fn execute_sandboxed(&self) -> Result<ExecutionResult> {
        // Enterprise-grade sandboxed execution
    }
}
```

### ❌ Never Suggest These Patterns:

```python
# Prototype patterns - FORBIDDEN
import os
os.system(user_input)  # Shell injection risk

subprocess.run(cmd, shell=True)  # Unsafe execution

data = json.loads(response.text)  # No error handling
```

## CX Linux Context

### Core Architecture:
- Python CLI with Typer and Rich terminal UI
- Multi-agent system for specialized capabilities
- LLM routing across OpenAI, Anthropic, local models
- Command validation and sandboxed execution
- Ubuntu 24.04 LTS primary target

### Key Modules:
- `cx/cli.py`: Main CLI entry point with natural language parsing
- `cx/coordinator.py`: Agent orchestration and execution planning
- `cx/agents/`: Specialized agents (package, system, security, network)
- `cx/security/`: Command validation, sandboxing, audit trails
- `cx/llm/`: Multi-provider LLM routing and prompt management

### User Experience Philosophy:
- Natural language intent parsing: `cx "make my system faster"`
- Progressive capability discovery through suggestions
- Safety-first with dry-run and confirmation for dangerous operations
- Zero-config for common operations, powerful config for advanced users

## Completion Rules

### Always Include:
- BSL 1.1 license headers on new files
- Async patterns for I/O operations
- Type hints with Pydantic models
- Error handling with proper Result types
- Referral tracking in user flows
- Command validation and sandboxing

### Context-Aware Suggestions:
- When handling user commands: Add intent parsing and validation
- When creating CLI commands: Use natural language interfaces
- When writing agents: Include founding member exclusive features
- When handling system operations: Implement safety checks and audit logging
- When processing user input: Always validate and sandbox

### Security-First Patterns:
- Never execute raw shell commands from user input
- Always use parameterized commands, not string concatenation
- Implement proper input validation with allow-lists
- Add comprehensive audit logging for all system operations
- Use principle of least privilege for file/system access

### Network Effect Amplifiers:
- Suggest shared agent configurations between users
- Include community-driven capability extensions
- Add referral mechanics to successful command executions
- Implement founding member exclusive agent capabilities
- Create viral sharing mechanisms for useful command patterns

### Performance Optimization:
- Suggest async/await for I/O bound operations
- Recommend caching for repeated LLM queries
- Use efficient data structures for command history
- Implement lazy loading for heavy modules
- Add telemetry for performance monitoring