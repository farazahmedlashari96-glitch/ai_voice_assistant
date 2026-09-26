"""Phase 8 - Testing & evaluation.

    python manage.py evaluate

Runs the real STT -> LLM -> TTS chain on:
  * every audio file in evaluation/samples/   (accuracy of speech recognition + speed)
  * every line of evaluation/prompts.txt      (response speed + replies to rate by hand)

and reports, per the project's evaluation criteria: speech-recognition accuracy (Word
Error Rate, when a matching .txt with the expected words exists), response time versus the
2-5 second target, and a CSV with an empty `quality_score` column to rate replies 1-5.
"""
import csv
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from assistant.metrics import word_error_rate
from assistant.services import llm, stt, tts
from assistant.services.errors import ServiceError
from assistant.services.text_processing import clean_user_text

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".flac"}
COLUMNS = [
    "case", "type", "expected", "transcript", "wer", "reply",
    "stt_s", "llm_s", "tts_s", "total_s", "within_target", "error", "quality_score",
]


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path(settings.BASE_DIR) / path


class Command(BaseCommand):
    help = "Evaluate speech-recognition accuracy, response speed and reply quality."

    def add_arguments(self, parser):
        parser.add_argument("--audio-dir", default="evaluation/samples")
        parser.add_argument("--prompts", default="evaluation/prompts.txt")
        parser.add_argument("--report", default="evaluation/report.csv")
        parser.add_argument("--target", type=float, default=settings.RESPONSE_TIME_TARGET_SECONDS,
                            help="response-time target in seconds (default 5)")
        parser.add_argument("--no-tts", action="store_true", help="skip speech synthesis")

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        audio_dir, prompts_file = _path(options["audio_dir"]), _path(options["prompts"])
        audio_files = (
            sorted(p for p in audio_dir.iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS)
            if audio_dir.is_dir() else []
        )
        prompts = []
        if prompts_file.is_file():
            for line in prompts_file.read_text(encoding="utf-8").splitlines():
                if line.strip() and not line.lstrip().startswith("#"):
                    prompts.append(line.strip())
        if not audio_files and not prompts:
            raise CommandError(f"Nothing to evaluate. Add audio files to {audio_dir} or prompts to {prompts_file}.")

        with_tts, target = not options["no_tts"], options["target"]
        rows = [self._run(p.name, "audio", target, with_tts, audio=p) for p in audio_files]
        rows += [self._run(f"prompt {i}", "text", target, with_tts, text=t) for i, t in enumerate(prompts, 1)]

        report = _path(options["report"])
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        self._summary(rows, target)
        self.stdout.write(f"\nReport saved to {report}  (rate the replies in the quality_score column)")

    # ------------------------------------------------------------------
    def _run(self, name, kind, target, with_tts, audio: Path | None = None, text: str = "") -> dict:
        row = dict.fromkeys(COLUMNS, "")
        row.update(case=name, type=kind)
        started = time.perf_counter()
        try:
            if audio is not None:
                expected_file = audio.with_suffix(".txt")
                if expected_file.is_file():
                    row["expected"] = expected_file.read_text(encoding="utf-8").strip()
                t = time.perf_counter()
                text = stt.transcribe(audio.read_bytes(), audio.name)
                row["stt_s"] = round(time.perf_counter() - t, 2)
                row["transcript"] = text
                if row["expected"]:
                    row["wer"] = round(word_error_rate(row["expected"], text), 3)

            t = time.perf_counter()
            reply = llm.generate_reply([{"role": "user", "content": clean_user_text(text)}])
            row["llm_s"] = round(time.perf_counter() - t, 2)
            row["reply"] = reply

            if with_tts:
                t = time.perf_counter()
                tts.synthesize(reply)
                row["tts_s"] = round(time.perf_counter() - t, 2)

            total = time.perf_counter() - started
            row["total_s"] = round(total, 2)
            row["within_target"] = "yes" if total <= target else "no"
        except ServiceError as exc:
            row["error"] = exc.message

        self.stdout.write(self._line(row))
        return row

    @staticmethod
    def _line(row: dict) -> str:
        if row["error"]:
            return f"[FAIL] {row['case']}: {row['error']}"
        parts = [f"{label} {row[key]}s" for label, key in
                 (("STT", "stt_s"), ("LLM", "llm_s"), ("TTS", "tts_s"), ("total", "total_s")) if row[key] != ""]
        wer = f"  WER {row['wer']}" if row["wer"] != "" else ""
        flag = "OK  " if row["within_target"] == "yes" else "SLOW"
        return f"[{flag}] {row['case']}: {'  '.join(parts)}{wer}"

    def _summary(self, rows: list[dict], target: float) -> None:
        ok = [r for r in rows if not r["error"]]

        def avg(key):
            values = [r[key] for r in ok if r[key] != ""]
            return f"{sum(values) / len(values):.2f}" if values else "-"

        wers = [r["wer"] for r in ok if r["wer"] != ""]
        within = sum(1 for r in ok if r["within_target"] == "yes")
        self.stdout.write("\n=== Summary ===")
        self.stdout.write(f"Cases: {len(rows)}   failed: {len(rows) - len(ok)}")
        if wers:
            self.stdout.write(f"Speech recognition: average WER {sum(wers) / len(wers):.3f} "
                              f"(accuracy about {100 * (1 - sum(wers) / len(wers)):.1f}%) over {len(wers)} file(s)")
        else:
            self.stdout.write("Speech recognition: no expected-text files found, WER not calculated")
        self.stdout.write(f"Average seconds -> STT {avg('stt_s')}  LLM {avg('llm_s')}  TTS {avg('tts_s')}  total {avg('total_s')}")
        if ok:
            self.stdout.write(f"Within the {target:g}s response-time target: {within}/{len(ok)}")
