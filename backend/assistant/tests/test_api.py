import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import groq
import httpx
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from assistant.services import groq_client

from .fakes import FakeGroq


def _status_error(cls, status):
    request = httpx.Request("POST", "https://api.groq.com/x")
    response = httpx.Response(status, request=request)
    return cls("boom", response=response, body=None)


def audio_file(size=20000, name="recording.wav", content_type="audio/wav"):
    return SimpleUploadedFile(name, b"\x00" * size, content_type=content_type)


class ApiTestCase(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.audio_dir = Path(tmp.name)
        override = override_settings(AUDIO_DIR=self.audio_dir, STORE_AUDIO=True)
        override.enable()
        self.addCleanup(override.disable)

    def use_fake(self, fake=None):
        self.fake = fake or FakeGroq()
        patcher = patch("assistant.services.groq_client.get_client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return self.fake

    def post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def stored(self, kind):
        folder = self.audio_dir / kind
        return list(folder.glob("*")) if folder.exists() else []


class ChatTests(ApiTestCase):
    def test_chat_returns_text_and_speech(self):
        self.use_fake()
        res = self.post_json("/api/chat/", {"message": "  what is the capital of france  "})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["user_text"], "What is the capital of france")
        self.assertEqual(body["reply"], "Paris is the capital of France.")
        self.assertFalse(body["exit"])
        self.assertTrue(base64.b64decode(body["audio"]).startswith(b"RIFF"))
        self.assertEqual(body["audio_mime"], "audio/wav")
        self.assertIn("llm_ms", body["timings"])
        self.assertIn("total_ms", body["timings"])
        self.assertEqual(len(self.stored("responses")), 1)   # Phase 2: reply stored

    def test_speak_false_skips_tts(self):
        fake = self.use_fake()
        body = self.post_json("/api/chat/", {"message": "hello", "speak": False}).json()
        self.assertIsNone(body["audio"])
        self.assertEqual(fake.tts_calls, [])

    def test_history_is_forwarded_to_the_llm(self):
        fake = self.use_fake()
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        self.post_json("/api/chat/", {"message": "and now?", "history": history, "speak": False})
        sent = fake.chat_calls[0]["messages"]
        self.assertEqual([m["role"] for m in sent], ["system", "user", "assistant", "user"])
        self.assertEqual(sent[-1]["content"], "And now?")

    def test_history_is_trimmed_and_starts_with_a_user_turn(self):
        fake = self.use_fake()
        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(30)]
        with override_settings(MAX_HISTORY_MESSAGES=5):
            self.post_json("/api/chat/", {"message": "next", "history": history, "speak": False})
        sent = fake.chat_calls[0]["messages"][1:]   # skip the system prompt
        self.assertEqual(sent[0]["role"], "user")
        self.assertLessEqual(len(sent), 5 + 1)

    def test_exit_command_skips_llm_and_says_goodbye(self):
        fake = self.use_fake()
        body = self.post_json("/api/chat/", {"message": "Exit."}).json()
        self.assertTrue(body["exit"])
        self.assertEqual(body["reply"], "Goodbye! Have a great day.")
        self.assertEqual(fake.chat_calls, [])

    def test_stop_also_exits(self):
        self.use_fake()
        self.assertTrue(self.post_json("/api/chat/", {"message": "stop"}).json()["exit"])

    def test_empty_message_is_no_input(self):
        self.use_fake()
        res = self.post_json("/api/chat/", {"message": "   "})
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "no_input")

    def test_bad_requests(self):
        self.use_fake()
        self.assertEqual(self.post_json("/api/chat/", {"message": 5}).status_code, 400)
        self.assertEqual(
            self.client.post("/api/chat/", data="{oops", content_type="application/json").status_code, 400
        )
        for bad in ("nope", [{"role": "system", "content": "x"}], [{"role": "user"}], {"a": 1}):
            res = self.post_json("/api/chat/", {"message": "hi", "history": bad})
            self.assertEqual(res.status_code, 400, bad)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get("/api/chat/").status_code, 405)

    def test_llm_failure_returns_502(self):
        self.use_fake(FakeGroq(llm_errors={
            "llama-3.3-70b-versatile": RuntimeError("boom"),
            "llama-3.1-8b-instant": RuntimeError("boom"),
        }))
        res = self.post_json("/api/chat/", {"message": "hello"})
        self.assertEqual(res.status_code, 502)
        self.assertEqual(res.json()["error"]["code"], "upstream_error")

    def test_falls_back_to_second_model_when_first_is_unavailable(self):
        fake = self.use_fake(FakeGroq(llm_errors={
            "llama-3.3-70b-versatile": _status_error(groq.NotFoundError, 404),
        }))
        res = self.post_json("/api/chat/", {"message": "hello", "speak": False})
        self.assertEqual(res.status_code, 200)
        self.assertEqual([c["model"] for c in fake.chat_calls], ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"])

    def test_tts_failure_keeps_the_text_reply(self):
        self.use_fake(FakeGroq(tts_error=RuntimeError("tts down")))
        res = self.post_json("/api/chat/", {"message": "hello"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNone(body["audio"])
        self.assertTrue(body["tts_error"])
        self.assertEqual(body["reply"], "Paris is the capital of France.")

    @override_settings(GROQ_API_KEY="")
    def test_missing_api_key_is_a_clear_503(self):
        res = self.post_json("/api/chat/", {"message": "hello"})
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["error"]["code"], "config_error")


class VoiceTests(ApiTestCase):
    def test_voice_turn_end_to_end(self):
        fake = self.use_fake()
        res = self.client.post("/api/voice/", {"audio": audio_file(), "speak": "true"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["transcript"], "What is the capital of France?")
        self.assertEqual(body["reply"], "Paris is the capital of France.")
        self.assertTrue(body["audio"])
        for key in ("stt_ms", "llm_ms", "tts_ms", "total_ms"):
            self.assertIn(key, body["timings"])
        self.assertEqual(fake.stt_calls[0]["file"][0], "recording.wav")
        self.assertEqual(fake.stt_calls[0]["model"], "whisper-large-v3-turbo")

    def test_recording_is_stored_as_wav(self):
        self.use_fake()
        self.client.post("/api/voice/", {"audio": audio_file()})
        saved = self.stored("recordings")
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].suffix, ".wav")

    def test_history_is_read_from_form_data(self):
        fake = self.use_fake()
        history = json.dumps([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello!"}])
        self.client.post("/api/voice/", {"audio": audio_file(), "history": history, "speak": "false"})
        self.assertEqual([m["role"] for m in fake.chat_calls[0]["messages"]], ["system", "user", "assistant", "user"])

    def test_filename_extension_follows_content_type(self):
        fake = self.use_fake()
        self.client.post("/api/voice/", {"audio": audio_file(name="blob", content_type="audio/mp4")})
        self.assertEqual(fake.stt_calls[0]["file"][0], "recording.mp4")

    def test_missing_audio_is_400(self):
        self.use_fake()
        self.assertEqual(self.client.post("/api/voice/", {}).status_code, 400)

    def test_tiny_recording_is_no_input(self):
        self.use_fake()
        res = self.client.post("/api/voice/", {"audio": audio_file(size=100)})
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "no_input")

    def test_oversized_recording_is_413(self):
        self.use_fake()
        with override_settings(MAX_AUDIO_BYTES=10000):
            res = self.client.post("/api/voice/", {"audio": audio_file(size=20000)})
        self.assertEqual(res.status_code, 413)

    def test_empty_transcript_is_unclear_audio(self):
        self.use_fake(FakeGroq(transcript=""))
        res = self.client.post("/api/voice/", {"audio": audio_file()})
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.json()["error"]["code"], "unclear_audio")

    def test_whisper_hallucination_on_silence_is_dropped(self):
        segments = [{"text": "Thank you.", "no_speech_prob": 0.9, "avg_logprob": -1.5}]
        self.use_fake(FakeGroq(transcript="Thank you.", segments=segments))
        res = self.client.post("/api/voice/", {"audio": audio_file()})
        self.assertEqual(res.json()["error"]["code"], "unclear_audio")

    def test_spoken_exit_command(self):
        fake = self.use_fake(FakeGroq(transcript="Exit."))
        body = self.client.post("/api/voice/", {"audio": audio_file()}).json()
        self.assertTrue(body["exit"])
        self.assertEqual(fake.chat_calls, [])

    def test_stt_language_setting_is_forwarded(self):
        fake = self.use_fake()
        with override_settings(STT_LANGUAGE="ur"):
            self.client.post("/api/voice/", {"audio": audio_file()})
        self.assertEqual(fake.stt_calls[0]["language"], "ur")


class HealthTests(ApiTestCase):
    def test_health(self):
        body = self.client.get("/api/health/").json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["response_time_target_ms"], 5000)
        self.assertIn("groq_configured", body)


class ErrorTranslationTests(SimpleTestCase):
    def test_sdk_errors_map_to_friendly_codes(self):
        request = httpx.Request("POST", "https://api.groq.com/x")
        cases = [
            (_status_error(groq.AuthenticationError, 401), "auth_error", 502),
            (_status_error(groq.RateLimitError, 429), "rate_limited", 429),
            (groq.APIConnectionError(request=request), "upstream_unavailable", 503),
            (groq.APITimeoutError(request=request), "upstream_timeout", 504),
            (_status_error(groq.InternalServerError, 500), "upstream_error", 502),
        ]
        for exc, code, status in cases:
            err = groq_client.translate_error(exc, "test")
            self.assertEqual((err.code, err.status), (code, status), type(exc).__name__)
