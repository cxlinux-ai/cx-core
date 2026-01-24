# Voice Input for Cortex

Cortex supports voice commands using speech-to-text, allowing you to install software and ask questions using your voice.

## Quick Start

```bash
# Install voice dependencies
pip install cortex-linux[voice]

# Start voice mode
cortex voice

# Or use voice for a single command
cortex install --mic
```

## Requirements

- **Python 3.10+**
- **Microphone** - Any USB or built-in microphone
- **Voice dependencies** - Installed separately (see below)

## Installation

Voice support is an optional feature. Install the voice dependencies with:

```bash
pip install cortex-linux[voice]
```

Or install dependencies individually:

```bash
pip install faster-whisper sounddevice pynput numpy
```

**Note:** On Linux, you may need to install PortAudio for audio support:
```bash
# Ubuntu/Debian
sudo apt install libportaudio2 portaudio19-dev

# Fedora
sudo dnf install portaudio portaudio-devel
```

### First Run

On first use, Cortex will automatically download the default Whisper model (`base.en`, ~140MB). This happens without any user prompt and is stored in `~/.cortex/models/`. Subsequent runs use the cached model, so downloads only happen once per model.

## Usage

### Voice Mode (Continuous)

Enter continuous voice mode where you can speak multiple commands:

```bash
cortex voice
```

**Controls:**
- **F9** - Start/stop recording
- **Ctrl+C** - Exit voice mode

**Example session:**
```text
$ cortex voice
CX ✓ Voice mode active. Press F9 to speak, Ctrl+C to exit.
CX │ Listening...

[Press F9]
CX │ Recording ●●○ (Press F9 to stop)

[Speak: "Install nginx"]
[Press F9]

CX ⠋ Transcribing...
Heard: Install nginx

CX │ Installing: nginx
CX ⠋ Understanding request...
...
```

### Single Voice Command

Use `--mic` flag for a single voice input:

```bash
# Install via voice
cortex install --mic

# Ask a question via voice
cortex ask --mic
```

### Single Recording Mode

Record one command and exit:

```bash
cortex voice --single
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CORTEX_WHISPER_MODEL` | `base.en` | Whisper model to use |

### Available Models

| Model | Size | Speed | Accuracy | Language |
|-------|------|-------|----------|----------|
| `tiny.en` | 39MB | Fastest | Fair | English only |
| `base.en` | 140MB | Fast | Good (default) | English only |
| `small.en` | 466MB | Medium | Better | English only |
| `medium.en` | 1.5GB | Slow | Best | English only |
| `tiny` | 39MB | Fastest | Fair | Multilingual |
| `base` | 290MB | Fast | Good | Multilingual |
| `small` | 968MB | Medium | Better | Multilingual |
| `medium` | 3GB | Slow | Best | Multilingual |
| `large` | 6GB | Very slow | Excellent | Multilingual |

#### Model Selection & Downloading

When you run `cortex voice` for the first time, the system **automatically downloads and caches** the default model (`base.en`). No manual intervention is required. The model is stored in `~/.cortex/models/` and reused on subsequent runs.

**Choosing a Model:**

Even if you have multiple models installed locally, you must explicitly choose which one to use—there is no interactive selection dialog. You can switch models in two ways:

1. **Using environment variable** (persistent for your session):
```bash
export CORTEX_WHISPER_MODEL=small.en
cortex voice
```

2. **Using command parameter** (one-time override):
```bash
cortex voice --model medium.en
```

If neither is specified, the system always defaults to `base.en`. To see which models you have installed:

```bash
ls -lh ~/.cortex/models/
```

#### Uninstalling Models

To completely remove a downloaded model from your machine:

```bash
# Remove a specific model
rm ~/.cortex/models/base.en.pt

# Remove all Whisper models
rm -rf ~/.cortex/models/

# View all downloaded models
ls -lh ~/.cortex/models/
```

**Model filename format:** `{model_name}.pt` (e.g., `base.en.pt`, `small.en.pt`)

After deletion, the model will be automatically re-downloaded the next time you use `cortex voice` with that model.

### Config File

Add to `~/.cortex/config.yaml`:

```yaml
voice:
  model: "base.en"
  hotkey: "f9"
  sample_rate: 16000
```

## How It Works

1. **Hotkey Detection** - Uses `pynput` library to listen for F9 (no root required)
2. **Audio Capture** - Records via `sounddevice` at 16kHz mono
3. **Speech-to-Text** - Transcribes using `faster-whisper` (OpenAI Whisper optimized)
4. **Command Processing** - Passes transcribed text to Cortex LLM interpreter
5. **Execution** - Normal Cortex workflow (dry-run by default)

```text
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│      F9      │───>│    Record    │───>│  Transcribe  │
│   Hotkey     │    │    Audio     │    │   (Whisper)  │
└──────────────┘    └──────────────┘    └──────────────┘
                                               │
                                               ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Execute    │<───│   Generate   │<───│   LLM Parse  │
│   Commands   │    │   Commands   │    │   Request    │
└──────────────┘    └──────────────┘    └──────────────┘
```

## Troubleshooting

### "No microphone found"

**Linux:**
```bash
# Check ALSA devices
arecord -l

# Install ALSA utilities
sudo apt install alsa-utils pulseaudio
```

**macOS:**
- Check System Preferences > Security & Privacy > Microphone
- Grant terminal app microphone access

### "Voice dependencies not installed"

```bash
pip install cortex-linux[voice]
```

### "Model download failed"

Check internet connection and try:
```bash
# Manually download model
python -c "from faster_whisper import WhisperModel; WhisperModel('base.en')"
```

### Recording quality issues

- Speak clearly and at normal volume
- Reduce background noise
- Position microphone 6-12 inches from mouth
- Try a different microphone

### Hotkey not working

On Linux, you may need to run with elevated permissions or use X11:
```bash
# Check if running in Wayland (hotkeys may not work)
echo $XDG_SESSION_TYPE

# For Wayland, consider using X11 or alternative input method
```

## Privacy

- **Local Processing** - All speech-to-text happens locally on your machine
- **No Audio Uploads** - Audio is never sent to external servers
- **Model Storage** - Whisper models stored in `~/.cortex/models/`

## Limitations

- English language only (using `.en` models)
- Requires ~150MB-1.5GB disk space for models
- CPU-based inference (no GPU acceleration by default)
- Push-to-talk only (no continuous listening for privacy)

## API Reference

### VoiceInputHandler

```python
from cortex.voice import VoiceInputHandler

# Create handler
handler = VoiceInputHandler(
    model_name="base.en",  # default
    sample_rate=16000,
    hotkey="f9",
)

# Single recording
text = handler.record_single()

# Continuous mode
def on_transcription(text):
    print(f"You said: {text}")

handler.start_voice_mode(on_transcription)
```

### Factory Function

```python
from cortex.voice import get_voice_handler

handler = get_voice_handler(
    model_name="base.en",
    sample_rate=16000,
    hotkey="f9",
)
```

## See Also

- [Getting Started Guide](guides/Getting-Started.md)
- [CLI Commands Reference](COMMANDS.md)
- [Configuration Guide](CONFIGURATION.md)

