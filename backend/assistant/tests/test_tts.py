import io
import wave
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from assistant.services import tts
from assistant.services.errors import ServiceError

from .fakes import FakeGroq, make_wav


def frames(wav_bytes: bytes) -> int:
    with wave.open(io.BytesIO(wav_bytes)) as wav:
        return wav.getnframes()


class WavMergeTests(SimpleTestCase):
    def test_merge_concatenates_audio(self):
        merged = tts.merge_wavs([make_wav(0.1), make_wav(0.2)])
        self.assertEqual(frames(merged), frames(make_wav(0.1)) + frames(make_wav(0.2)))

    def test_merge_accepts_streamed_wav_with_unknown_length(self):
        merged = tts.merge_wavs([make_wav(0.1, unknown_size=True), make_wav(0.1, unknown_size=True)])
        self.assertEqual(frames(merged), 2 * frames(make_wav(0.1)))

    def test_merge_rejects_mismatched_formats(self):
        with self.assertRaises(ServiceError):
            tts.merge_wavs([make_wav(rate=24000), make_wav(rate=16000)])

    def test_merge_rejects_garbage(self):
        with self.assertRaises(ServiceError):
            tts.merge_wavs([b"not a wav file at all"])


@override_settings(GROQ_TTS_MODEL="canopylabs/orpheus-v1-english", GROQ_TTS_VOICE="autumn")
class SynthesizeTests(SimpleTestCase):
    def test_long_text_is_chunked_under_200_chars(self):
        fake = FakeGroq()
        text = " ".join(f"Sentence number {i} is here." for i in range(12))
        with patch("assistant.services.groq_client.get_client", return_value=fake):
            wav = tts.synthesize(text)
        self.assertGreater(len(fake.tts_calls), 1)
        self.assertTrue(all(len(c["input"]) <= 200 for c in fake.tts_calls))
        self.assertTrue(all(c["response_format"] == "wav" for c in fake.tts_calls))
        self.assertEqual(frames(wav), len(fake.tts_calls) * frames(make_wav()))

    def test_nothing_to_speak(self):
        with patch("assistant.services.groq_client.get_client", return_value=FakeGroq()):
            with self.assertRaises(ServiceError):
                tts.synthesize("*** ...")
