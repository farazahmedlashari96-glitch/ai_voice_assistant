import csv
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from assistant.metrics import word_error_rate

from .fakes import FakeGroq


class WerTests(SimpleTestCase):
    def test_identical_text_is_zero(self):
        self.assertEqual(word_error_rate("Hello, World!", "hello world"), 0.0)

    def test_substitution_deletion_insertion(self):
        self.assertAlmostEqual(word_error_rate("the cat sat", "the dog sat"), 1 / 3)
        self.assertAlmostEqual(word_error_rate("the cat sat", "the cat"), 1 / 3)
        self.assertAlmostEqual(word_error_rate("the cat", "the big cat"), 1 / 2)

    def test_empty_reference(self):
        self.assertEqual(word_error_rate("", ""), 0.0)
        self.assertEqual(word_error_rate("", "something"), 1.0)


class EvaluateCommandTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / "hello.wav").write_bytes(b"\x00" * 100)
        (self.dir / "hello.txt").write_text("What is the capital of France")
        (self.dir / "prompts.txt").write_text("# comment\nWhat is 2 plus 2?\n\n")

    def run_command(self, fake, **kwargs):
        out = StringIO()
        with patch("assistant.services.groq_client.get_client", return_value=fake):
            call_command(
                "evaluate", audio_dir=str(self.dir), prompts=str(self.dir / "prompts.txt"),
                report=str(self.dir / "report.csv"), stdout=out, **kwargs,
            )
        return out.getvalue()

    def test_reports_wer_timings_and_csv(self):
        output = self.run_command(FakeGroq(transcript="What is the capital of France"))
        self.assertIn("average WER 0.000", output)
        self.assertIn("Within the 5s response-time target: 2/2", output)
        rows = list(csv.DictReader((self.dir / "report.csv").open()))
        self.assertEqual([r["type"] for r in rows], ["audio", "text"])
        self.assertEqual(rows[0]["wer"], "0.0")
        self.assertEqual(rows[1]["reply"], "Paris is the capital of France.")
        self.assertIn("quality_score", rows[0])

    def test_wer_reflects_recognition_mistakes(self):
        output = self.run_command(FakeGroq(transcript="What is the capital of Spain"))
        self.assertIn("average WER 0.167", output)

    def test_failures_are_reported_not_raised(self):
        output = self.run_command(FakeGroq(transcript=""))
        self.assertIn("[FAIL] hello.wav", output)

    def test_nothing_to_evaluate(self):
        with self.assertRaises(CommandError):
            call_command("evaluate", audio_dir=str(self.dir / "none"), prompts=str(self.dir / "none.txt"))
