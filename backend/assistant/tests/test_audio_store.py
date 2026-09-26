import os
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from assistant.services import audio_store


class AudioStoreTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_saves_recording_and_response_in_their_folders(self):
        with override_settings(AUDIO_DIR=self.dir, STORE_AUDIO=True):
            rec = audio_store.save_recording(b"abc", ".wav")
            reply = audio_store.save_response(b"def")
        self.assertEqual(rec.parent.name, "recordings")
        self.assertTrue(rec.name.startswith("input_") and rec.suffix == ".wav")
        self.assertEqual(reply.parent.name, "responses")
        self.assertEqual(rec.read_bytes(), b"abc")

    def test_disabled_storage_writes_nothing(self):
        with override_settings(AUDIO_DIR=self.dir, STORE_AUDIO=False):
            self.assertIsNone(audio_store.save_recording(b"abc"))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_cleanup_keeps_only_the_newest_files(self):
        folder = self.dir / "recordings"
        folder.mkdir()
        for i in range(6):
            path = folder / f"input_{i}.wav"
            path.write_bytes(b"x")
            os.utime(path, (1000 + i, 1000 + i))
        (folder / ".gitkeep").write_bytes(b"")
        audio_store.cleanup(folder, keep=2)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), [".gitkeep", "input_4.wav", "input_5.wav"])

    def test_unwritable_folder_does_not_raise(self):
        blocker = self.dir / "file"
        blocker.write_bytes(b"x")  # AUDIO_DIR points at a file, so mkdir fails
        with override_settings(AUDIO_DIR=blocker, STORE_AUDIO=True):
            self.assertIsNone(audio_store.save_recording(b"abc"))
