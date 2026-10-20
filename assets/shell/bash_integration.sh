#!/bin/bash
# Copyright (c) 2026 AI Venture Holdings LLC
# Licensed under the Business Source License 1.1
#
# CX Terminal Shell Integration for Bash
# Captures stderr of failed commands for 'cx fix'

# Only run in interactive shells
if [[ $- != *i* ]]; then
    return
fi

__cx_err_capture() {
    local exit_code=$?
    
    if [ $exit_code -ne 0 ]; then
        if [ -s "$HOME/.cx/stderr.tmp" ]; then
            # Get the last command from history
            local last_cmd=$(history 1 | sed 's/^[ ]*[0-9]*[ ]*//')
            
            # Don't capture if it was 'cx fix' or similar
            if [[ "$last_cmd" =~ ^cx\ fix ]]; then
                : > "$HOME/.cx/stderr.tmp"
                return
            fi

            {
                echo "Command: $last_cmd"
                echo "Exit Code: $exit_code"
                echo "--- Stderr ---"
                cat "$HOME/.cx/stderr.tmp"
            } > "$HOME/.cx/last_error"
        fi
    fi
    # Clear for next command
    : > "$HOME/.cx/stderr.tmp"
}

# Inject into PROMPT_COMMAND
if [[ ! "$PROMPT_COMMAND" =~ __cx_err_capture ]]; then
    if [[ -z "$PROMPT_COMMAND" ]]; then
        PROMPT_COMMAND="__cx_err_capture"
    else
        PROMPT_COMMAND="__cx_err_capture; $PROMPT_COMMAND"
    fi
fi

# Ensure .cx directory exists
mkdir -p "$HOME/.cx"

# Global stderr capture
# Note: we use 'tee' to ensure the user still sees the error on their screen.
# We redirect stderr (2) through tee which also writes to stderr.tmp
exec 2> >(tee "$HOME/.cx/stderr.tmp" >&2)
