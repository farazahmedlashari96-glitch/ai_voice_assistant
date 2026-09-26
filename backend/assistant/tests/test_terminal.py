"""Terminal mode (Python): microphone recorder, speaker playback and `manage.py talk`."""
import io
import sys
import tempfile
import wave
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from assistant.services import player
from assistant.services.errors import AudioDeviceError, NoInputError
from assistant.services.recorder import MicrophoneRecorder, encode_wav

from .fakes import FakeGroq, make_wav

RATE = 16000
BLOCK = 1600  # 0.1 s


class FakeStream:
    """A pretend microphone that yields one constant-volume block per amplitude."""

    def __init__(self, amplitudes):
        self._amplitudes = iter(amplitudes)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, frames):
        amplitude = next(self._amplitudes)  # StopIteration = the recorder read more than expected
        return np.full((frames, 1), int(amplitude * 32767), dtype=np.int16), False


def recorder_for(*parts, **kwargs):
    amplitudes = [amp for amp, count in parts for _ in range(count)]
    return MicrophoneRecorder(sample_rate=RATE, stream_factory=lambda: FakeStream(amplitudes), **kwargs)


def wav_info(data: bytes):
    with wave.open(io.BytesIO(data)) as wav:
        return wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()


class RecorderTests(SimpleTestCase):
    def test_records_speech_and_stops_after_a_pause(self):
        recorder = recorder_for((0.005, 4), (0.2, 5), (0.005, 14))  # noise, speech, 1.4 s pause
        wav = recorder.record()
        self.assertEqual(wav_info(wav), (1, 2, RATE, 23 * BLOCK))

    def test_adapts_to_a_noisy_room(self):
        # Constant background hum (0.03) must not count as speech; only the loud part does.
        recorder = recorder_for((0.03, 4), (0.03, 3), (0.3, 3), (0.03, 14))
        _, _, _, frames = wav_info(recorder.record())
        self.assertEqual(frames, (4 + 3 + 14) * BLOCK)  # 4 pre-roll + 3 speech + 14 pause blocks

    def test_no_speech_raises_no_input(self):
        recorder = recorder_for((0.005, 10), no_speech_seconds=1.0)
        with self.assertRaises(NoInputError):
            recorder.record()

    def test_max_length_cuts_off_a_very_long_utterance(self):
        recorder = recorder_for((0.005, 4), (0.3, 100), max_seconds=3.0)
        _, _, _, frames = wav_info(recorder.record())
        self.assertEqual(frames, 30 * BLOCK)

    def test_microphone_failure_becomes_audio_device_error(self):
        def broken():
            raise RuntimeError("device busy")

        recorder = MicrophoneRecorder(sample_rate=RATE, stream_factory=broken)
        with self.assertRaises(AudioDeviceError) as ctx:
            recorder.record()
        self.assertIn("device busy", ctx.exception.message)

    def test_missing_sounddevice_gives_install_hint(self):
        with patch.dict(sys.modules, {"sounddevice": None}):
            with self.assertRaises(AudioDeviceError) as ctx:
                MicrophoneRecorder(sample_rate=RATE).record()
        self.assertIn("sounddevice", ctx.exception.message)

    def test_encode_wav_round_trip(self):
        samples = np.array([0, 1000, -1000, 32767], dtype=np.int16)
        self.assertEqual(wav_info(encode_wav(samples, RATE)), (1, 2, RATE, 4))


class PlayerTests(SimpleTestCase):
    def test_plays_wav_through_sounddevice(self):
        calls = []
        fake = SimpleNamespace(play=lambda audio, rate: calls.append((audio.shape, rate)), wait=lambda: calls.append("wait"))
        with patch.dict(sys.modules, {"sounddevice": fake}):
            player.play_wav(make_wav(0.1, rate=24000))
        self.assertEqual(calls, [((2400, 1), 24000), "wait"])

    def test_bad_audio_and_missing_device(self):
        fake = SimpleNamespace(play=lambda *a: None, wait=lambda: None)
        with patch.dict(sys.modules, {"sounddevice": fake}):
            with self.assertRaises(AudioDeviceError):
                player.play_wav(b"not a wav")
        with patch.dict(sys.modules, {"sounddevice": None}):
            with self.assertRaises(AudioDeviceError):
                player.play_wav(make_wav())


class ScriptedRecorder:
    """Stands in for MicrophoneRecorder: each item is text 'spoken' by the user or an exception."""

    def __init__(self, fake_groq, script):
        self.fake, self.script = fake_groq, list(script)

    def __call__(self, *args, **kwargs):
        return self

    def record(self):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        self.fake.transcript = item   # what Whisper will "hear"
        return make_wav(0.5, rate=16000)


class TalkCommandTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.audio_dir = Path(tmp.name)
        override = override_settings(AUDIO_DIR=self.audio_dir, STORE_AUDIO=True)
        override.enable()
        self.addCleanup(override.disable)
        self.fake = FakeGroq()
        patcher = patch("assistant.services.groq_client.get_client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        played = patch("assistant.management.commands.talk.play_wav")
        self.played = played.start()
        self.addCleanup(played.stop)

    def run_talk(self, script=None, inputs=None, **options):
        out = StringIO()
        patches = []
        if script is not None:
            patches.append(patch("assistant.management.commands.talk.MicrophoneRecorder", ScriptedRecorder(self.fake, script)))
        if inputs is not None:
            patches.append(patch("builtins.input", side_effect=inputs))
        for p in patches:
            p.start()
        try:
            call_command("talk", stdout=out, **options)
        finally:
            for p in patches:
                p.stop()
        return out.getvalue()

    def test_voice_conversation_until_exit(self):
        out = self.run_talk(script=["What is the capital of France?", "Exit."])
        self.assertIn("You: What is the capital of France?", out)
        self.assertIn("Assistant: Paris is the capital of France.", out)
        self.assertIn("Assistant: Goodbye! Have a great day.", out)
        self.assertIn("STT", out)
        self.assertEqual(self.played.call_count, 2)                         # reply + goodbye spoken
        self.assertEqual(len(list((self.audio_dir / "recordings").glob("*.wav"))), 2)  # Phase 2

    def test_conversation_memory(self):
        self.run_talk(script=["hello", "and now?", "stop"])
        roles = [m["role"] for m in self.fake.chat_calls[1]["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])

    def test_text_mode_needs_no_microphone(self):
        out = self.run_talk(inputs=["hello there", "exit"], text=True, no_tts=True)
        self.assertIn("Assistant: Paris is the capital of France.", out)
        self.assertEqual(self.fake.stt_calls, [])
        self.played.assert_not_called()

    def test_ends_after_repeated_silence(self):
        out = self.run_talk(script=[NoInputError()] * 3)
        self.assertIn("I haven't heard anything", out)
        self.assertEqual(self.fake.chat_calls, [])

    def test_api_failure_is_reported_and_the_loop_continues(self):
        fake_errors = {"llama-3.3-70b-versatile": RuntimeError("x"), "llama-3.1-8b-instant": RuntimeError("x")}
        self.fake.llm_errors = fake_errors
        out = self.run_talk(script=["hello", "exit"])
        self.assertIn("Error:", out)
        self.assertIn("Goodbye", out)

    def test_microphone_failure_stops_with_a_hint(self):
        with self.assertRaises(CommandError) as ctx:
            self.run_talk(script=[AudioDeviceError("no microphone found")])
        self.assertIn("--text", str(ctx.exception))


@override_settings(GROQ_API_KEY="")
class TalkMissingKeyTests(SimpleTestCase):
    def test_missing_api_key_stops_with_a_clear_message(self):
        with patch("builtins.input", side_effect=["hello"]):
            with self.assertRaises(CommandError) as ctx:
                call_command("talk", text=True, no_tts=True, stdout=StringIO())
        self.assertIn("GROQ_API_KEY", str(ctx.exception))
