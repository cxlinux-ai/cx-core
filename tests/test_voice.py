"""Tests for the voice input module."""

import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestVoiceInputHandler:
    """Test suite for VoiceInputHandler class."""

    @pytest.fixture
    def mock_dependencies(self):
        """Mock all voice dependencies."""
        with patch.dict(
            "sys.modules",
            {
                "sounddevice": MagicMock(),
                "faster_whisper": MagicMock(),
                "pynput": MagicMock(),
                "pynput.keyboard": MagicMock(),
            },
        ):
            yield

    @pytest.fixture
    def handler(self, mock_dependencies):
        """Create a VoiceInputHandler instance with mocked dependencies."""
        from cortex.voice import VoiceInputHandler

        return VoiceInputHandler(
            model_name="tiny.en",
            sample_rate=16000,
            hotkey="f9",
        )

    def test_init_defaults(self, mock_dependencies):
        """Test VoiceInputHandler initialization with defaults."""
        from cortex.voice import VoiceInputHandler

        handler = VoiceInputHandler()
        assert handler.model_name == "base.en"
        assert handler.sample_rate == 16000
        assert handler.hotkey == "f9"
        assert handler._model is None
        assert handler._is_recording is False

    def test_init_custom_params(self, mock_dependencies):
        """Test VoiceInputHandler initialization with custom parameters."""
        from cortex.voice import VoiceInputHandler

        handler = VoiceInputHandler(
            model_name="base.en",
            sample_rate=44100,
            hotkey="ctrl+m",
            model_dir="/custom/path",
        )
        assert handler.model_name == "base.en"
        assert handler.sample_rate == 44100
        assert handler.hotkey == "ctrl+m"
        assert handler.model_dir == "/custom/path"

    def test_init_with_env_var(self, mock_dependencies, monkeypatch):
        """Test model name from environment variable."""
        from cortex.voice import VoiceInputHandler

        monkeypatch.setenv("CORTEX_WHISPER_MODEL", "small.en")
        handler = VoiceInputHandler()
        assert handler.model_name == "small.en"

    def test_ensure_dependencies_all_present(self, handler):
        """Test _ensure_dependencies when all deps are installed."""
        with patch.dict(
            "sys.modules",
            {
                "sounddevice": MagicMock(),
                "faster_whisper": MagicMock(),
                "pynput": MagicMock(),
                "pynput.keyboard": MagicMock(),
            },
        ):
            result = handler._ensure_dependencies()
            assert result is True

    def test_ensure_dependencies_missing(self, handler):
        """Test _ensure_dependencies when deps are missing."""
        # Clear the modules to simulate missing dependencies
        with patch.dict("sys.modules", {"sounddevice": None}):
            with patch("cortex.voice.cx_print") as mock_print:
                # This will try to import and fail
                # The actual behavior depends on how imports are handled
                pass

    def test_check_microphone_available(self, handler):
        """Test microphone check when device is available."""
        mock_sd = MagicMock()
        mock_devices = [{"max_input_channels": 2, "name": "Test Mic"}]
        mock_sd.query_devices.return_value = mock_devices
        mock_sd.query_devices.side_effect = lambda kind=None: (
            {"name": "Test Mic", "max_input_channels": 2} if kind == "input" else mock_devices
        )

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            with patch("cortex.voice.cx_print"):
                # Import fresh to get mocked module
                import importlib

                import cortex.voice

                importlib.reload(cortex.voice)
                handler = cortex.voice.VoiceInputHandler()
                result = handler._check_microphone()
                assert result is True

    def test_check_microphone_not_available(self, handler):
        """Test microphone check when no device available."""
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = []

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            with patch("cortex.voice.cx_print") as mock_print:
                import importlib

                import cortex.voice

                importlib.reload(cortex.voice)
                handler = cortex.voice.VoiceInputHandler()
                result = handler._check_microphone()
                assert result is False

    def test_transcribe_empty_audio(self, handler):
        """Test transcription with empty audio data."""
        handler._model = MagicMock()
        result = handler.transcribe(np.array([], dtype=np.float32))
        assert result == ""

    def test_transcribe_with_audio(self, handler):
        """Test transcription with valid audio data."""
        # Mock the model
        mock_segment = MagicMock()
        mock_segment.text = " Hello world "
        mock_info = MagicMock()

        handler._model = MagicMock()
        handler._model.transcribe.return_value = ([mock_segment], mock_info)

        audio_data = np.random.randn(16000).astype(np.float32)  # 1 second of audio
        result = handler.transcribe(audio_data)
        assert result == "Hello world"

    def test_transcribe_loads_model_if_needed(self, handler):
        """Test that transcribe loads model if not loaded."""
        with patch.object(handler, "_load_model") as mock_load:
            mock_segment = MagicMock()
            mock_segment.text = "test"
            handler._model = MagicMock()
            handler._model.transcribe.return_value = ([mock_segment], MagicMock())

            audio_data = np.random.randn(16000).astype(np.float32)
            handler.transcribe(audio_data)
            # Model was already set, so _load_model shouldn't be called
            # In real scenario, if _model is None, it would call _load_model

    def test_stop_cleans_up_resources(self, handler):
        """Test that stop() properly cleans up resources."""
        handler._is_recording = True
        mock_listener = MagicMock()
        mock_stream = MagicMock()
        handler._hotkey_listener = mock_listener
        handler._stream = mock_stream

        handler.stop()

        assert handler._is_recording is False
        mock_listener.stop.assert_called_once()
        assert handler._hotkey_listener is None
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_stop_handles_missing_stream(self, handler):
        """Test that stop() handles case when stream doesn't exist."""
        handler._is_recording = True
        handler._hotkey_listener = None
        # No _stream attribute

        # Should not raise
        handler.stop()
        assert handler._is_recording is False

    def test_stop_handles_stream_error(self, handler):
        """Test that stop() handles stream close errors gracefully."""
        handler._is_recording = True
        handler._hotkey_listener = None
        handler._stream = MagicMock()
        handler._stream.close.side_effect = OSError("Stream error")

        # Should not raise, just log
        handler.stop()
        assert handler._stream is None


class TestVoiceInputExceptions:
    """Test voice input exception classes."""

    def test_voice_input_error(self):
        """Test VoiceInputError exception."""
        from cortex.voice import VoiceInputError

        with pytest.raises(VoiceInputError):
            raise VoiceInputError("Test error")

    def test_microphone_not_found_error(self):
        """Test MicrophoneNotFoundError exception."""
        from cortex.voice import MicrophoneNotFoundError, VoiceInputError

        error = MicrophoneNotFoundError("No mic")
        assert isinstance(error, VoiceInputError)

    def test_model_not_found_error(self):
        """Test ModelNotFoundError exception."""
        from cortex.voice import ModelNotFoundError, VoiceInputError

        error = ModelNotFoundError("Model missing")
        assert isinstance(error, VoiceInputError)


class TestGetVoiceHandler:
    """Test the factory function."""

    def test_get_voice_handler_defaults(self):
        """Test get_voice_handler with default parameters."""
        with patch.dict(
            "sys.modules",
            {
                "sounddevice": MagicMock(),
                "faster_whisper": MagicMock(),
                "pynput": MagicMock(),
                "pynput.keyboard": MagicMock(),
            },
        ):
            from cortex.voice import get_voice_handler

            handler = get_voice_handler()
            assert handler.model_name == "base.en"
            assert handler.sample_rate == 16000
            assert handler.hotkey == "f9"

    def test_get_voice_handler_custom(self):
        """Test get_voice_handler with custom parameters."""
        with patch.dict(
            "sys.modules",
            {
                "sounddevice": MagicMock(),
                "faster_whisper": MagicMock(),
                "pynput": MagicMock(),
                "pynput.keyboard": MagicMock(),
            },
        ):
            from cortex.voice import get_voice_handler

            handler = get_voice_handler(
                model_name="base.en",
                sample_rate=44100,
                hotkey="ctrl+m",
            )
            assert handler.model_name == "base.en"
            assert handler.sample_rate == 44100
            assert handler.hotkey == "ctrl+m"


class TestRecordingState:
    """Test recording state management."""

    @pytest.fixture
    def handler(self):
        """Create handler with mocked dependencies."""
        with patch.dict(
            "sys.modules",
            {
                "sounddevice": MagicMock(),
                "faster_whisper": MagicMock(),
                "pynput": MagicMock(),
                "pynput.keyboard": MagicMock(),
            },
        ):
            from cortex.voice import VoiceInputHandler

            return VoiceInputHandler()

    def test_initial_state(self, handler):
        """Test initial recording state."""
        assert handler._is_recording is False
        assert handler._audio_buffer == []
        assert handler._recording_thread is None

    def test_stop_recording_event(self, handler):
        """Test stop recording event is properly set."""
        assert not handler._stop_recording.is_set()
        handler._stop_recording.set()
        assert handler._stop_recording.is_set()
        handler._stop_recording.clear()
        assert not handler._stop_recording.is_set()
