#!/bin/bash
# CX Terminal Shell Integration for Bash
# Source this in ~/.bashrc: source /usr/share/cx-terminal/shell-integration/cx.bash

# OSC escape sequences for CX Terminal
__cx_osc() {
    printf '\033]%s\007' "$1"
}

# Mark the start of a command block
__cx_block_start() {
    local cmd="$1"
    __cx_osc "133;A"  # Mark prompt end
    __cx_osc "133;C"  # Command start
    __cx_osc "1337;SetMark"
    __cx_osc "777;cx;block;start;cmd=$cmd;time=$(date +%s)"
}

# Mark the end of a command block
__cx_block_end() {
    local exit_code="$?"
    __cx_osc "133;D;$exit_code"  # Command end with exit code
    __cx_osc "777;cx;block;end;exit=$exit_code;time=$(date +%s)"
    return $exit_code
}

# Mark the start of the prompt
__cx_prompt_start() {
    __cx_osc "133;P"  # Prompt start
    __cx_osc "777;cx;prompt;start"
}

# Set up the prompt hooks
__cx_setup() {
    # Preserve existing PROMPT_COMMAND
    if [[ -n "$PROMPT_COMMAND" ]]; then
        PROMPT_COMMAND="__cx_block_end; $PROMPT_COMMAND; __cx_prompt_start"
    else
        PROMPT_COMMAND="__cx_block_end; __cx_prompt_start"
    fi

    # Hook into DEBUG trap for command start
    trap '__cx_block_start "$BASH_COMMAND"' DEBUG

    # Set terminal title
    __cx_osc "0;CX Terminal - $USER@$HOSTNAME"

    # Enable semantic zones
    __cx_osc "777;cx;features;blocks=1;ai=1;agents=1"
}

# Current working directory reporting
__cx_report_cwd() {
    __cx_osc "7;file://$HOSTNAME$(pwd)"
    __cx_osc "777;cx;cwd;path=$(pwd)"
}

# Add CWD reporting to cd
cx_cd() {
    builtin cd "$@" && __cx_report_cwd
}
alias cd='cx_cd'

# AI command helpers
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

# Initialize
if [[ "$TERM_PROGRAM" == "CXTerminal" ]] || [[ -n "$CX_TERMINAL" ]]; then
    __cx_setup
    __cx_report_cwd
fi
