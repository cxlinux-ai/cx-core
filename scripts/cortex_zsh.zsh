# Cortex Zsh shell integration
# Binds Ctrl+L to send current input to Cortex and replace it with a suggestion

_cortex_suggest() {
    local input="$BUFFER"
    local suggestion

    suggestion="$(cortex _shell_suggest "$input" 2>/dev/null)"

    if [[ -n "$suggestion" ]]; then
        BUFFER="$suggestion"
        CURSOR=${#BUFFER}
    fi
}

zle -N _cortex_suggest
bindkey '^L' _cortex_suggest