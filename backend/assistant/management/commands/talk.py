"""Terminal mode (Python): talk to the assistant with your microphone.

    python manage.py talk                 # speak; say "exit" or "stop" to quit
    python manage.py talk --text          # type instead of speaking (no microphone needed)
    python manage.py talk --no-tts        # print replies without speaking them
    python manage.py talk --list-devices  # show audio input devices

Same workflow as the web app, using the same modules:
capture voice -> STT -> LLM API -> response -> TTS -> play audio + show text.
"""
import base64
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from assistant.services import audio_store, pipeline, stt
from assistant.services.errors import (
    AudioDeviceError,
    NoInputError,
    ServiceError,
    UnclearAudioError,
)
from assistant.services.player import play_wav
from assistant.services.recorder import MicrophoneRecorder, list_input_devices

MAX_SILENT_TURNS = 3   # end the conversation after this many empty recordings in a row
FATAL_CODES = {"config_error", "auth_error"}


class Command(BaseCommand):
    help = "Voice conversation in the terminal (microphone -> STT -> LLM -> TTS -> speakers)."

    def add_arguments(self, parser):
        parser.add_argument("--text", action="store_true", help="type instead of speaking")
        parser.add_argument("--no-tts", action="store_true", help="do not speak replies")
        parser.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
        parser.add_argument("--device", default=None, help="microphone device id or name")

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        try:
            if options["list_devices"]:
                self.stdout.write(list_input_devices())
                return
        except AudioDeviceError as exc:
            raise CommandError(exc.message)

        text_mode, speak = options["text"], not options["no_tts"]
        recorder = None if text_mode else MicrophoneRecorder(device=options["device"])

        self.stdout.write("=" * 56)
        self.stdout.write(" AI Voice Assistant  -  say or type 'exit' or 'stop' to quit")
        self.stdout.write("=" * 56)

        history: list[dict] = []
        silent_turns = 0
        while True:
            try:
                user_text, stt_ms = self._listen(recorder)
                silent_turns = 0
                result = pipeline.process_text_turn(
                    history, user_text, speak=speak,
                    timings={"stt_ms": stt_ms} if stt_ms is not None else None,
                )
                self._show(result, echo_user=recorder is not None)
                self._play(result)
                if result["exit"]:
                    return
                history = pipeline.trim_history(
                    [*history,
                     {"role": "user", "content": result["user_text"]},
                     {"role": "assistant", "content": result["reply"]}]
                )
            except AudioDeviceError as exc:
                raise CommandError(f"{exc.message}\nTip: use --text to test without a microphone.")
            except (NoInputError, UnclearAudioError) as exc:
                silent_turns += 1
                if silent_turns >= MAX_SILENT_TURNS:
                    self.stdout.write("Assistant: I haven't heard anything for a while. Goodbye!")
                    return
                self.stdout.write(f"   {exc.message}")
            except ServiceError as exc:
                if exc.code in FATAL_CODES:
                    raise CommandError(exc.message)
                self.stdout.write(self.style.ERROR(f"   Error: {exc.message}"))
            except (KeyboardInterrupt, EOFError):
                self.stdout.write("\nInterrupted. Goodbye!")
                return

    # ------------------------------------------------------------------
    def _listen(self, recorder):
        """Return (text, stt_ms): typed text, or the transcript of a microphone recording."""
        if recorder is None:
            return input("You (type): "), None

        self.stdout.write("🎤 Listening... speak now")
        wav = recorder.record()                       # 1. capture voice input (WAV)
        audio_store.save_recording(wav)               # Phase 2: store audio files
        self.stdout.write("⏳ Transcribing...")
        started = time.perf_counter()
        text = stt.transcribe(wav, "recording.wav")   # 2. speech -> text
        return text, round((time.perf_counter() - started) * 1000)

    def _show(self, result: dict, echo_user: bool) -> None:
        if echo_user:  # what the microphone was understood as (typed text is already on screen)
            self.stdout.write(f"You: {result['user_text']}")
        self.stdout.write(f"Assistant: {result['reply']}")
        t = result["timings"]
        parts = [f"{label} {t[key] / 1000:.1f}s" for label, key in
                 (("STT", "stt_ms"), ("LLM", "llm_ms"), ("TTS", "tts_ms")) if key in t]
        target = settings.RESPONSE_TIME_TARGET_SECONDS
        verdict = "within" if t["total_ms"] / 1000 <= target else "over"
        parts.append(f"total {t['total_ms'] / 1000:.1f}s ({verdict} the {target:g}s target)")
        self.stdout.write(f"   ⏱ {' · '.join(parts)}")

    def _play(self, result: dict) -> None:
        if result["tts_error"]:
            self.stdout.write(f"   (voice unavailable: {result['tts_error']})")
        if not result["audio"]:
            return
        try:
            play_wav(base64.b64decode(result["audio"]))   # 6. output audio
        except AudioDeviceError as exc:
            self.stdout.write(f"   (could not play audio: {exc.message})")
