#!/usr/bin/env bash
# CX Terminal: record the 30-second demo (demo/cx-30s.tape) with VHS.
#
# Refuses to record unless `cx` can reach a real AI backend: the local model
# (`cx ai download`), ANTHROPIC_API_KEY or OLLAMA_HOST. The recording shows only
# what that backend actually answers.
#
# Usage: demo/record-30s.sh            (from the repo root or anywhere)
# Needs: vhs (https://github.com/charmbracelet/vhs), ttyd, ffmpeg, a `cx` on PATH.
# Output: demo/out/cx-30s.gif, demo/out/cx-30s.mp4, demo/out/transcript.txt
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { echo "record-30s: $*" >&2; exit 1; }

for tool in vhs ttyd ffmpeg cx; do
    command -v "$tool" >/dev/null 2>&1 || fail "'$tool' not found on PATH."
done

model="${XDG_CACHE_HOME:-$HOME/.cache}/cx-linux/models/cxlinux-ai-7b-Q4_K_M.gguf"
if [ ! -e "$model" ] && [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${OLLAMA_HOST:-}" ]; then
    fail "no AI backend. Run 'cx ai download' (local, ~5 GB) or set ANTHROPIC_API_KEY / OLLAMA_HOST."
fi

vhs validate demo/cx-30s.tape >/dev/null || fail "demo/cx-30s.tape does not parse (vhs validate)."

mkdir -p demo/out
transcript="demo/out/transcript.txt"
: > "$transcript"

# Preflight: the same three prompts, outside VHS, so a broken backend fails here
# with a readable error instead of producing an empty GIF.
probe() {
    local label="$1"; shift
    local start end
    start=$(date +%s)
    {
        echo "\$ $(printf "%q " "$@")"
        "$@"
    } >>"$transcript" 2>&1 || fail "'$*' failed; see $transcript"
    end=$(date +%s)
    echo "  ok  $label ($((end - start))s)"
    echo >>"$transcript"
}

echo "Preflight (real backend):"
probe "answer"  cx ask 'how do I check disk usage' </dev/null
probe "confirm" cx ask -d 'show memory usage' </dev/null
probe "install" cx ask 'install nginx' </dev/null

grep -q '^  \$ ' "$transcript" || fail "no answer contained a command; see $transcript"
grep -q 'No AI backend' "$transcript" && fail "cx reported no AI backend; see $transcript"

echo "Recording..."
VHS_NO_SANDBOX="${VHS_NO_SANDBOX:-}" vhs demo/cx-30s.tape

duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 demo/out/cx-30s.mp4)
echo "Done: demo/out/cx-30s.gif, demo/out/cx-30s.mp4 (${duration%.*}s), $transcript"
