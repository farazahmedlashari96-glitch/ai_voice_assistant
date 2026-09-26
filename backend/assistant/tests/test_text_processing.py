from django.test import SimpleTestCase

from assistant.services.text_processing import (
    clean_for_speech,
    clean_user_text,
    is_exit_command,
    split_for_tts,
)


class UserTextTests(SimpleTestCase):
    def test_clean_user_text(self):
        self.assertEqual(clean_user_text("  what   is  python  "), "What is python")
        self.assertEqual(clean_user_text("   "), "")

    def test_exit_commands(self):
        for phrase in ("Exit.", "please stop!", "Goodbye", "bye", "quit"):
            self.assertTrue(is_exit_command(phrase), phrase)

    def test_exit_word_inside_sentence_is_not_exit(self):
        self.assertFalse(is_exit_command("stop the music"))
        self.assertFalse(is_exit_command("what is exit velocity"))


class SpeechTextTests(SimpleTestCase):
    def test_removes_markdown_urls_and_brackets(self):
        text = "**Hello** [docs](http://x.com) see https://a.b `code` [whisper] done"
        self.assertEqual(clean_for_speech(text), "Hello docs see link code done")

    def test_split_respects_limit_and_order(self):
        text = " ".join(f"This is sentence number {i}." for i in range(20))
        chunks = split_for_tts(text, limit=100, max_chars=10_000)
        self.assertTrue(all(len(c) <= 100 for c in chunks))
        self.assertEqual(" ".join(chunks), text)

    def test_split_handles_one_very_long_sentence(self):
        chunks = split_for_tts("word " * 200, limit=50, max_chars=10_000)
        self.assertTrue(all(len(c) <= 50 for c in chunks))

    def test_split_truncates_at_a_sentence_boundary(self):
        chunks = split_for_tts("First sentence here. " * 100, limit=190, max_chars=100)
        joined = " ".join(chunks)
        self.assertLessEqual(len(joined), 100)
        self.assertTrue(joined.endswith("."))

    def test_split_drops_punctuation_only_chunks(self):
        self.assertEqual(split_for_tts("... ---"), [])
