"""
Cortex Linux Voice Input Module

Provides voice command capability using faster-whisper for speech-to-text.
Supports push-to-talk (F9 by default) for low-latency voice input.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from cortex.branding import console, cx_print


class VoiceInputError(Exception):
    """Base exception for voice input errors."""

    pass


class MicrophoneNotFoundError(VoiceInputError):
    """Raised when no microphone is available."""

    pass


class ModelNotFoundError(VoiceInputError):
    """Raised when the whisper model cannot be loaded."""

    pass


class VoiceInputHandler:
    """Handles voice input with push-to-talk and speech-to-text transcription.

    Uses faster-whisper for efficient, accurate transcription with minimal
    resource usage. Supports F9 push-to-talk hotkey by default.

    Attributes:
        model_name: Whisper model to use (base.en, small.en, medium.en)
        sample_rate: Audio sample rate in Hz (default: 16000)
        hotkey: Push-to-talk hotkey (default: f9)
    """

    def __init__(
        self,
        model_name: str | None = None,
        sample_rate: int = 16000,
        hotkey: str | None = None,
        model_dir: str | None = None,
    ):
        """Initialize the voice input handler.

        Args:
            model_name: Whisper model name (base.en, small.en, medium.en).
                       Defaults to CORTEX_WHISPER_MODEL env var or 'base.en'.
            sample_rate: Audio sample rate in Hz. Default 16000.
            hotkey: Push-to-talk hotkey. Default 'f9'.
                   Respects CORTEX_VOICE_HOTKEY env var if hotkey arg not provided.
            model_dir: Directory to store whisper models.
                      Defaults to ~/.cortex/models/
        """
        self.model_name = model_name or os.environ.get("CORTEX_WHISPER_MODEL", "base.en")
        self.sample_rate = sample_rate
        self.hotkey = (hotkey or os.environ.get("CORTEX_VOICE_HOTKEY", "f9")).lower()
        self.model_dir = model_dir or str(Path.home() / ".cortex" / "models")

        # Recording state
        self._is_recording = False
        self._audio_buffer: list[Any] = []  # numpy arrays when recording
        self._recording_thread: threading.Thread | None = None
        self._stop_recording = threading.Event()
        self._stream = None

        # Whisper model (lazy loaded)
        self._model = None

        # Hotkey listener
        self._hotkey_listener = None
        self._hotkey_callback: Callable[[str], None] | None = None

    def _ensure_dependencies(self) -> bool:
        """Check if voice dependencies are installed.

        Raises:
            VoiceInputError: If required dependencies are missing.

        Returns:
            True if all dependencies are available.
        """
        missing = []

        try:
            import sounddevice  # noqa: F401
        except ImportError:
            missing.append("sounddevice")

        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            missing.append("faster-whisper")

        try:
            from pynput import keyboard  # noqa: F401
        except ImportError:
            missing.append("pynput")

        if missing:
            error_msg = f"Missing voice dependencies: {', '.join(missing)}"
            install_cmd = f"pip install {' '.join(missing)}"
            raise VoiceInputError(
                f"{error_msg}\n\nInstall with: pip install cortex-linux[voice]\n"
                f"Or: {install_cmd}"
            )

        return True

    def _load_model(self) -> None:
        """Load the whisper model.

        Raises:
            ModelNotFoundError: If model cannot be loaded.
        """
        from faster_whisper import WhisperModel

        # Model sizes in MB (int8 quantized) with accuracy descriptions
        model_info = {
            "tiny.en": {"size": 39, "desc": "fastest, good for clear speech"},
            "base.en": {"size": 140, "desc": "balanced speed/accuracy"},
            "small.en": {"size": 466, "desc": "better accuracy"},
            "medium.en": {"size": 1534, "desc": "high accuracy"},
            "tiny": {"size": 39, "desc": "fastest, multilingual"},
            "base": {"size": 290, "desc": "balanced, multilingual"},
            "small": {"size": 968, "desc": "better accuracy, multilingual"},
            "medium": {"size": 3090, "desc": "high accuracy, multilingual"},
            "large": {"size": 6000, "desc": "best accuracy, multilingual"},
        }

        info = model_info.get(self.model_name, {"size": "unknown", "desc": ""})
        size_str = f"{info['size']} MB" if isinstance(info["size"], int) else info["size"]
        desc_str = f" - {info['desc']}" if info["desc"] else ""

        cx_print(
            f"Loading whisper model '{self.model_name}' ({size_str}{desc_str})...",
            "info",
        )

        # Ensure model directory exists
        os.makedirs(self.model_dir, exist_ok=True)

        try:
            # Show download progress with progress bar
            from rich.progress import Progress

            with Progress() as progress:
                task = progress.add_task(
                    f"[cyan]Downloading {self.model_name}...",
                    total=None,
                )

                self._model = WhisperModel(
                    self.model_name,
                    device="cpu",
                    compute_type="int8",
                    download_root=self.model_dir,
                )
                progress.update(task, completed=True)

            cx_print(
                f"✓ Model '{self.model_name}' loaded successfully.",
                "success",
            )
            if info["desc"]:
                cx_print(
                    f"  {info['desc'].capitalize()} | Size: {size_str} | Tip: Use --model flag to try different models",
                    "dim",
                )
        except Exception as e:
            raise ModelNotFoundError(
                f"Failed to load whisper model '{self.model_name}': {e}"
            ) from e

    def _check_microphone(self) -> bool:
        """Check if a microphone is available.

        Raises:
            MicrophoneNotFoundError: If no microphone is available or error occurs.

        Returns:
            True if microphone is available.
        """
        import sounddevice as sd

        try:
            devices = sd.query_devices()
            input_devices = [d for d in devices if d["max_input_channels"] > 0]

            if not input_devices:
                raise MicrophoneNotFoundError("No microphone found. Please connect a microphone.")

            default = sd.query_devices(kind="input")
            cx_print(f"Using microphone: {default['name']}", "info")
            return True

        except MicrophoneNotFoundError:
            raise
        except Exception as e:
            raise MicrophoneNotFoundError(f"Error checking microphone: {e}") from e

    def _start_recording(self) -> None:
        """Start recording audio from microphone."""
        import numpy as np  # Import locally for optional dependency
        import sounddevice as sd

        self._audio_buffer = []
        self._stop_recording.clear()
        self._is_recording = True
        self._numpy = np  # Store for use in callback

        def audio_callback(indata, frames, time_info, status):
            if status:
                logging.debug("Audio status: %s", status)
            if self._is_recording:
                # Limit buffer size to prevent memory issues (max ~60 seconds)
                if len(self._audio_buffer) < 60 * self.sample_rate // 1024:
                    self._audio_buffer.append(indata.copy())
                else:
                    self._stop_recording.set()

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype=self._numpy.float32,
                callback=audio_callback,
                blocksize=1024,
            )
            self._stream.start()
        except PermissionError as e:
            self._is_recording = False
            raise MicrophoneNotFoundError(
                "Permission denied to access microphone. "
                "On Linux, add user to 'audio' group: sudo usermod -a -G audio $USER"
            ) from e
        except Exception as e:
            self._is_recording = False
            raise MicrophoneNotFoundError(f"Failed to start recording: {e}") from e

    def _stop_recording_stream(self) -> Any:
        """Stop recording and return the audio data.

        Returns:
            Numpy array of recorded audio samples.
        """
        import numpy as np

        self._is_recording = False

        if hasattr(self, "_stream") and self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logging.debug("Error closing stream: %s", e)
            finally:
                self._stream = None

        if not self._audio_buffer:
            return np.array([], dtype=np.float32)

        # Concatenate all audio chunks
        try:
            audio_data = np.concatenate(self._audio_buffer, axis=0)
            return audio_data.flatten()
        finally:
            # Always clear buffer to prevent memory leaks
            self._audio_buffer = []

    def transcribe(self, audio_data: Any) -> str:
        """Transcribe audio data to text.

        Args:
            audio_data: Numpy array of audio samples (float32, mono).

        Returns:
            Transcribed text string.

        Raises:
            ModelNotFoundError: If model is not loaded.
        """
        import numpy as np

        if self._model is None:
            self._load_model()

        if len(audio_data) == 0:
            return ""

        # faster-whisper expects float32 audio normalized to [-1, 1]
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        # Model should be loaded at this point
        if self._model is None:
            raise ModelNotFoundError("Model must be loaded before transcription")

        segments, _ = self._model.transcribe(
            audio_data,
            beam_size=5,
            language="en",
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 300,
                "speech_pad_ms": 200,
            },
            condition_on_previous_text=False,  # Prevents repetition
            no_speech_threshold=0.6,
        )

        # Collect all segment texts
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        return " ".join(text_parts).strip()

    def record_and_transcribe(self) -> str:
        """Record audio until stopped and transcribe it.

        This is a blocking call that records until _stop_recording is set.

        Returns:
            Transcribed text from the recording.
        """
        self._start_recording()

        # Wait for stop signal
        self._stop_recording.wait()

        # Get audio and transcribe
        audio_data = self._stop_recording_stream()

        if len(audio_data) < self.sample_rate * 0.5:  # Less than 0.5 seconds
            return ""

        cx_print("Transcribing...", "thinking")
        text = self.transcribe(audio_data)

        return text

    def _recording_indicator(self) -> None:
        """Show a recording indicator with animated dots."""
        dots = 0
        indicators = ["●○○", "●●○", "●●●", "○●●", "○○●", "○○○"]
        while self._is_recording:
            indicator = indicators[dots % len(indicators)]
            console.print(
                f"Recording {indicator} (Press {self.hotkey.upper()} to stop)",
                end="\r",
            )
            dots += 1
            time.sleep(0.2)
        # Clear the line
        console.print(" " * 70, end="\r")

    def _get_hotkey_key(self) -> Optional[keyboard.Key]:  # noqa: F821, UP045
        """Get the pynput key object for the configured hotkey."""
        from pynput import keyboard

        # Map hotkey string to pynput key
        hotkey_map = {
            "f1": keyboard.Key.f1,
            "f2": keyboard.Key.f2,
            "f3": keyboard.Key.f3,
            "f4": keyboard.Key.f4,
            "f5": keyboard.Key.f5,
            "f6": keyboard.Key.f6,
            "f7": keyboard.Key.f7,
            "f8": keyboard.Key.f8,
            "f9": keyboard.Key.f9,
            "f10": keyboard.Key.f10,
            "f11": keyboard.Key.f11,
            "f12": keyboard.Key.f12,
            "pause": keyboard.Key.pause,
            "insert": keyboard.Key.insert,
            "home": keyboard.Key.home,
            "end": keyboard.Key.end,
            "pageup": keyboard.Key.page_up,
            "pagedown": keyboard.Key.page_down,
        }

        return hotkey_map.get(self.hotkey)

    def _setup_hotkey(self, on_transcription: Callable[[str], None]) -> None:
        """Set up the push-to-talk hotkey listener.

        Args:
            on_transcription: Callback function called with transcribed text.
        """
        from pynput import keyboard

        self._hotkey_callback = on_transcription
        recording_lock = threading.Lock()
        target_key = self._get_hotkey_key()

        if target_key is None:
            cx_print(f"Unknown hotkey: {self.hotkey}. Using F9.", "warning")
            target_key = keyboard.Key.f9
            self.hotkey = "f9"

        def on_press(key):
            if key == target_key:
                with recording_lock:
                    if not self._is_recording:
                        # Start recording - set flag BEFORE starting thread
                        self._is_recording = True
                        self._stop_recording.clear()

                        # Start indicator thread
                        indicator_thread = threading.Thread(
                            target=self._recording_indicator,
                            daemon=True,
                        )
                        indicator_thread.start()

                        # Start recording thread
                        self._recording_thread = threading.Thread(
                            target=self._recording_worker,
                            daemon=True,
                        )
                        self._recording_thread.start()
                    else:
                        # Stop recording
                        self._stop_recording.set()

        listener = keyboard.Listener(on_press=on_press)
        self._hotkey_listener = listener
        listener.start()

    def _recording_worker(self) -> None:
        """Worker thread for recording and transcription."""
        text = ""
        try:
            text = self.record_and_transcribe()

            if text:
                console.print(f"\n[bold cyan]Heard:[/bold cyan] {text}\n")
            else:
                cx_print("No speech detected. Try speaking louder or closer to the mic.", "warning")

        except Exception as e:
            cx_print(f"Recording error: {e}", "error")
        finally:
            self._is_recording = False
            # Always signal completion to unblock waiting callers
            if self._hotkey_callback:
                self._hotkey_callback(text)

    def start_voice_mode(self, on_transcription: Callable[[str], None]) -> None:
        """Start continuous voice input mode.

        Listens for the hotkey and transcribes speech when triggered.

        Args:
            on_transcription: Callback called with transcribed text.

        Raises:
            VoiceInputError: If dependencies are missing.
            MicrophoneNotFoundError: If microphone is not available.
            ModelNotFoundError: If model cannot be loaded.
        """
        self._ensure_dependencies()
        self._check_microphone()
        self._load_model()

        cx_print(
            f"Voice mode active. Press {self.hotkey.upper()} to speak, Ctrl+C to exit.", "success"
        )
        cx_print("Listening...", "info")

        self._setup_hotkey(on_transcription)

        try:
            # Keep the main thread alive
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            cx_print("\nVoice mode exited.", "info")
        finally:
            self.stop()

    def record_single(self) -> str:
        """Record a single voice input and return the transcribed text.

        This is a blocking call that waits for the user to press the hotkey
        to start and stop recording.

        Returns:
            Transcribed text from the recording.

        Raises:
            VoiceInputError: If dependencies are missing.
            MicrophoneNotFoundError: If microphone is not available.
            ModelNotFoundError: If model cannot be loaded.
        """
        self._ensure_dependencies()
        self._check_microphone()
        self._load_model()

        cx_print(f"Press {self.hotkey.upper()} to start recording...", "info")

        result = {"text": ""}
        done_event = threading.Event()

        def on_transcription(text: str) -> None:
            result["text"] = text
            done_event.set()

        self._setup_hotkey(on_transcription)

        try:
            # Wait for transcription to complete
            done_event.wait()
        except KeyboardInterrupt:
            cx_print("\nCancelled.", "info")
        finally:
            self.stop()
            # Brief pause to ensure keyboard listener fully releases
            # and any buffered key events are cleared
            time.sleep(0.1)

        return result["text"]

    def stop(self) -> None:
        """Stop the voice input handler and clean up resources."""
        self._is_recording = False
        self._stop_recording.set()

        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception as e:
                logging.debug("Error stopping hotkey listener: %s", e)
            self._hotkey_listener = None

        if hasattr(self, "_stream") and self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except OSError as e:
                logging.debug("Error closing audio stream: %s", e)
            self._stream = None


def get_voice_handler(
    model_name: str | None = None,
    sample_rate: int = 16000,
    hotkey: str | None = None,
) -> VoiceInputHandler:
    """Factory function to create a VoiceInputHandler.

    Args:
        model_name: Whisper model name. Defaults to CORTEX_WHISPER_MODEL env var or 'base.en'.
        sample_rate: Audio sample rate. Default 16000.
        hotkey: Push-to-talk hotkey. Default 'f9'.
               Respects CORTEX_VOICE_HOTKEY env var if hotkey arg not provided.

    Returns:
        Configured VoiceInputHandler instance.
    """
    return VoiceInputHandler(
        model_name=model_name,
        sample_rate=sample_rate,
        hotkey=hotkey,
    )
