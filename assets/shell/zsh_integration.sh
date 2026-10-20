#!/bin/zsh
# Copyright (c) 2026 AI Venture Holdings LLC
# Licensed under the Business Source License 1.1
#
# CX Terminal Shell Integration for Zsh
# Captures stderr of failed commands for 'cx fix'

# Only run in interactive shells
if [[ ! -o interactive ]]; then
    return
fi

__cx_err_capture_precmd() {
    local exit_code=$?
    
    if [[ $exit_code -ne 0 ]]; then
        if [[ -s "$HOME/.cx/stderr.tmp" ]]; then
            # In Zsh, the last command is available via fc
            local last_cmd=$(fc -ln -1)
            
            # Don't capture if it was 'cx fix' or similar
            if [[ "$last_cmd" =~ "cx fix" ]]; then
                : > "$HOME/.cx/stderr.tmp"
                return
            fi

            {
                echo "Command: ${last_cmd# }"
                echo "Exit Code: $exit_code"
                echo "--- Stderr ---"
                cat "$HOME/.cx/stderr.tmp"
            } > "$HOME/.cx/last_error"
        fi
    fi
    # Clear for next command
    : > "$HOME/.cx/stderr.tmp"
}

# Setup hooks
autoload -Uz add-zsh-hook
add-zsh-hook precmd __cx_err_capture_precmd

# Ensure .cx directory exists
mkdir -p "$HOME/.cx"

# Global stderr capture
exec 2> >(tee "$HOME/.cx/stderr.tmp" >&2)
