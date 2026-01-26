#!/bin/zsh
# CX Terminal Shell Integration for Zsh
# Source this in ~/.zshrc: source /usr/share/cx-terminal/shell-integration/cx.zsh

# OSC escape sequences for CX Terminal
__cx_osc() {
    print -n "\033]$1\007"
}

# Mark the start of a command block
__cx_block_start() {
    __cx_osc "133;C"
    __cx_osc "777;cx;block;start;cmd=${1};time=$(date +%s)"
}

# Mark the end of a command block
__cx_block_end() {
    local exit_code=$?
    __cx_osc "133;D;$exit_code"
    __cx_osc "777;cx;block;end;exit=$exit_code;time=$(date +%s)"
    return $exit_code
}

# CX Error Capture for cx fix
__CX_DIR="${HOME}/.cx"
__CX_LAST_ERROR="${__CX_DIR}/last_error"
mkdir -p "$__CX_DIR" 2>/dev/null

# Wrapper to run command and capture errors for cx fix
cxrun() {
    local tmp_err
    tmp_err=$(mktemp)
    eval "$@" 2> >(tee "$tmp_err" >&2)
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        {
            echo "Command: $*"
            echo "Exit code: $exit_code"
            echo "---"
            cat "$tmp_err"
        } > "$__CX_LAST_ERROR"
    fi
    rm -f "$tmp_err"
    return $exit_code
}

# Mark prompt boundaries
__cx_prompt_start() {
    __cx_osc "133;A"
    __cx_osc "777;cx;prompt;start"
}

__cx_prompt_end() {
    __cx_osc "133;B"
    __cx_osc "777;cx;prompt;end"
}

# Setup hooks
__cx_setup() {
    # Add to precmd (runs before prompt)
    autoload -Uz add-zsh-hook
    add-zsh-hook precmd __cx_precmd
    add-zsh-hook preexec __cx_preexec

    # Set terminal title
    __cx_osc "0;CX Terminal - $USER@$HOST"

    # Enable features
    __cx_osc "777;cx;features;blocks=1;ai=1;agents=1"
}

__cx_precmd() {
    __cx_block_end
    __cx_prompt_start
}

__cx_preexec() {
    __cx_prompt_end
    __cx_block_start "$1"
}

# CWD reporting
__cx_report_cwd() {
    __cx_osc "7;file://$HOST$(pwd)"
    __cx_osc "777;cx;cwd;path=$(pwd)"
}

# Override cd
cx_cd() {
    builtin cd "$@" && __cx_report_cwd
}
alias cd='cx_cd'

# AI helpers
cx_explain() {
    __cx_osc "777;cx;ai;explain;text=$*"
}

cx_suggest() {
    __cx_osc "777;cx;ai;suggest;query=$*"
}

cx_agent() {
    local agent="$1"
    shift
    __cx_osc "777;cx;agent;name=$agent;command=$*"
}

# Register completions for cx commands
_cx_explain() {
    _message "text to explain"
}
_cx_suggest() {
    _message "what you want to do"
}
_cx_agent() {
    local agents=(system file package network process git docker)
    _arguments "1:agent:($agents)" "*:command"
}

compdef _cx_explain cx_explain
compdef _cx_suggest cx_suggest
compdef _cx_agent cx_agent

# ============================================================================
# CX Quick Blocks - Type /python, /node, /react, etc. to scaffold environments
# ============================================================================

# Python environment setup
/python() {
    local name="${1:-my-python-project}"
    echo "🐍 Setting up Python environment..."

    if (( $+commands[cx] )); then
        cx new python "$name"
        cd "$name" 2>/dev/null || true
    else
        mkdir -p "$name" && cd "$name"
        python3 -m venv .venv
        echo "source .venv/bin/activate"
        source .venv/bin/activate 2>/dev/null || true
    fi
}

# Node.js environment setup
/node() {
    local name="${1:-my-node-project}"
    echo "📦 Setting up Node.js environment..."

    if (( $+commands[cx] )); then
        cx new node "$name"
        cd "$name" 2>/dev/null || true
    else
        mkdir -p "$name" && cd "$name"
        npm init -y
    fi
}

# React app setup
/react() {
    local name="${1:-my-react-app}"
    echo "⚛️  Setting up React app..."

    if (( $+commands[cx] )); then
        cx new react "$name"
        cd "$name" 2>/dev/null || true
    else
        npm create vite@latest "$name" -- --template react
        cd "$name" 2>/dev/null || true
    fi
}

# Next.js app setup
/nextjs() {
    local name="${1:-my-nextjs-app}"
    echo "▲ Setting up Next.js app..."

    if (( $+commands[cx] )); then
        cx new nextjs "$name"
        cd "$name" 2>/dev/null || true
    else
        npx create-next-app@latest "$name"
        cd "$name" 2>/dev/null || true
    fi
}

# FastAPI backend setup
/api() {
    local name="${1:-my-api}"
    echo "🚀 Setting up FastAPI backend..."

    if (( $+commands[cx] )); then
        cx new fastapi "$name"
        cd "$name" 2>/dev/null || true
    else
        mkdir -p "$name" && cd "$name"
        python3 -m venv .venv && source .venv/bin/activate
        pip install fastapi uvicorn
        cat > main.py << 'EOF'
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello World"}
EOF
        echo "Run with: uvicorn main:app --reload"
    fi
}

# Docker project setup
/docker() {
    local name="${1:-my-docker-project}"
    echo "🐳 Setting up Docker project..."

    if (( $+commands[cx] )); then
        cx new docker "$name"
        cd "$name" 2>/dev/null || true
    else
        mkdir -p "$name" && cd "$name"
        cat > Dockerfile << 'EOF'
FROM node:20-alpine
WORKDIR /app
COPY . .
CMD ["node", "index.js"]
EOF
        echo "Created Dockerfile"
    fi
}

# Go project setup
/go() {
    local name="${1:-my-go-project}"
    echo "🐹 Setting up Go project..."

    if (( $+commands[cx] )); then
        cx new go "$name"
        cd "$name" 2>/dev/null || true
    else
        mkdir -p "$name" && cd "$name"
        go mod init "$name"
        cat > main.go << 'EOF'
package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}
EOF
    fi
}

# Rust project setup
/rust() {
    local name="${1:-my-rust-project}"
    echo "🦀 Setting up Rust project..."

    if (( $+commands[cx] )); then
        cx new rust "$name"
        cd "$name" 2>/dev/null || true
    else
        cargo new "$name"
        cd "$name" 2>/dev/null || true
    fi
}

# SQLite database setup
/db() {
    local name="${1:-my-db-project}"
    echo "🗄️  Setting up SQLite database project..."

    if (( $+commands[cx] )); then
        cx new db "$name"
        cd "$name" 2>/dev/null || true
    else
        mkdir -p "$name" && cd "$name"
        touch data.db
        echo "SQLite database created at data.db"
    fi
}

# List available quick blocks
/help() {
    echo "CX Terminal Quick Blocks:"
    echo ""
    echo "  /python [name]  - Create Python project with uv/venv"
    echo "  /node [name]    - Create Node.js project"
    echo "  /react [name]   - Create React app with Vite"
    echo "  /nextjs [name]  - Create Next.js app"
    echo "  /api [name]     - Create FastAPI backend"
    echo "  /docker [name]  - Create Docker project"
    echo "  /go [name]      - Create Go project"
    echo "  /rust [name]    - Create Rust project"
    echo "  /db [name]      - Create SQLite database project"
    echo ""
    echo "Example: /python my-ml-project"
}

# Initialize
if [[ "$TERM_PROGRAM" == "CXTerminal" ]] || [[ -n "$CX_TERMINAL" ]]; then
    __cx_setup
    __cx_report_cwd
fi
