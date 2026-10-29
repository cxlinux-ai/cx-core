# CX demo recordings

| File | What it shows | AI output |
|---|---|---|
| `cx-30s.tape` + `record-30s.sh` | 30-second product demo: plain-English question → commands; `-d` → plan + `[y/N]` consent → run; "install nginx" → package search, nothing installed | **Live** from a real backend. The script refuses to record without one |

## Record the 30-second demo

```bash
cx ai download          # once: local model, ~5 GB (or set ANTHROPIC_API_KEY / OLLAMA_HOST)
demo/record-30s.sh      # needs vhs, ttyd, ffmpeg and cx on PATH
```

Output goes to `demo/out/` (git-ignored): `cx-30s.gif`, `cx-30s.mp4`, and `transcript.txt` (the preflight run's full text output, for checking what the recording shows).

Committed reference recording: `cx-30s.gif` (29 s) with its preflight transcript `cx-30s.transcript.txt` — recorded 2026-10-21 on Ubuntu 24.04, 2 vCPU / 8 GB, release build, local model `cxlinux-ai-7b-Q4_K_M.gguf`, no API key, no network calls by `cx`.

## What is and isn't in the frame

- Every answer is produced live by the backend at recording time. The local model decodes greedily, so it gives the same answer for the same prompt; cloud backends may vary.
- The model's thinking time is cut (`Hide`/`Show` in the tape). `time` stays on screen so the real latency of the recording machine is visible. Reference: about 50–60 s per answer for the local 7B model on a 2-vCPU cloud VM. Other hardware and the cloud backends were not measured.
- Not shown: the GUI "Tab moment" (instant fuzzy suggestions). It is not wired into the running terminal yet, so there is nothing real to record.
