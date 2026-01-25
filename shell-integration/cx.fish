# CX Terminal Shell Integration for Fish
# Source this in ~/.config/fish/config.fish: source /usr/share/cx-terminal/shell-integration/cx.fish

# OSC escape sequences for CX Terminal
function __cx_osc
    printf '\033]%s\007' $argv[1]
end

# Mark command block start
function __cx_block_start --on-event fish_preexec
    __cx_osc "133;C"
    __cx_osc "777;cx;block;start;cmd=$argv[1];time="(date +%s)
end

# Mark command block end
function __cx_block_end --on-event fish_postexec
    set -l exit_code $status
    __cx_osc "133;D;$exit_code"
    __cx_osc "777;cx;block;end;exit=$exit_code;time="(date +%s)
end

# Mark prompt boundaries
function __cx_prompt_start --on-event fish_prompt
    __cx_osc "133;A"
    __cx_osc "777;cx;prompt;start"
end

# CWD reporting
function __cx_report_cwd --on-variable PWD
    __cx_osc "7;file://"(hostname)(pwd)
    __cx_osc "777;cx;cwd;path="(pwd)
end

# Setup function
function __cx_setup
    # Set terminal title
    __cx_osc "0;CX Terminal - $USER@"(hostname)

    # Enable features
    __cx_osc "777;cx;features;blocks=1;ai=1;agents=1"
end

# AI helpers
function cx_explain -d "Explain text using CX AI"
    __cx_osc "777;cx;ai;explain;text=$argv"
end

function cx_suggest -d "Get command suggestions from CX AI"
    __cx_osc "777;cx;ai;suggest;query=$argv"
end

function cx_agent -d "Run CX Linux agent"
    set -l agent $argv[1]
    set -e argv[1]
    __cx_osc "777;cx;agent;name=$agent;command=$argv"
end

# Completions for cx commands
complete -c cx_agent -f -a "system file package network process git docker" -d "Agent name"

# Initialize
if test "$TERM_PROGRAM" = "CXTerminal"; or test -n "$CX_TERMINAL"
    __cx_setup
    __cx_report_cwd
end
