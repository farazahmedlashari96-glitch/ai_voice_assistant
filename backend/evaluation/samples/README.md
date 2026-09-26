# Test recordings for `python manage.py evaluate`

Put WAV files here (16 kHz mono works best) to measure **speech-recognition accuracy** and **response time**.

1. Use the app normally - every recording is saved in `backend/audio_files/recordings/`.
2. Copy a few of those `.wav` files into this folder.
3. Next to each one, create a text file with the words you actually said:
   `my_question.wav` -> `my_question.txt` containing `What is the capital of France`
4. Run `python manage.py evaluate`.

Try different inputs (short/long sentences, quiet/noisy room, fast/slow speech) as Phase 3 of the brief suggests.
A file without a `.txt` is still timed, but no accuracy (WER) is calculated for it.
