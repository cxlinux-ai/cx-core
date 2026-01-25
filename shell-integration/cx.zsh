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

# Initialize
if [[ "$TERM_PROGRAM" == "CXTerminal" ]] || [[ -n "$CX_TERMINAL" ]]; then
    __cx_setup
    __cx_report_cwd
fi
