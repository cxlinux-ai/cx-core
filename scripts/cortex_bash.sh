# Cortex Bash shell integration
# Binds Ctrl+L to send current input to Cortex and replace it with a suggestion

_cortex_suggest() {
    # READLINE_LINE contains the current command line
    local input="$READLINE_LINE"

    # Call cortex shell suggestion helper
    local suggestion
    suggestion="$(cortex _shell_suggest "$input" 2>/dev/null)"

    # If we got a suggestion, replace the current line
    if [[ -n "$suggestion" ]]; then
        READLINE_LINE="$suggestion"
        READLINE_POINT=${#READLINE_LINE}
    fi
}

# Bind Ctrl+L to cortex suggestion
bind -x '"\C-l": _cortex_suggest'
