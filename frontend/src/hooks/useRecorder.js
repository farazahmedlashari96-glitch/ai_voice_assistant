import { useCallback, useEffect, useRef, useState } from "react";
import { chunksToWavBlob } from "../audio/wav.js";

const WORKLET_URL = `${import.meta.env.BASE_URL}recorder-worklet.js`;

function micErrorMessage(err) {
  switch (err?.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Microphone access was blocked. Allow it in your browser's address bar and try again.";
    case "NotFoundError":
      return "No microphone was found on this device.";
    case "NotReadableError":
      return "The microphone is being used by another app.";
    default:
      return "Could not start the microphone.";
  }
}

const average = (values) => values.reduce((a, b) => a + b, 0) / (values.length || 1);

function rmsOf(samples) {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / (samples.length || 1));
}

/**
 * Functional requirement 1 - capture the user's voice from the microphone and
 * record it as a 16 kHz mono WAV file.
 *
 * Basic noise and pause handling: the background level is measured during the first
 * 0.4 s so the speech threshold adapts to the room; recording stops after `silenceMs`
 * of quiet once speech was heard, and gives up after `noSpeechMs` if nobody speaks.
 */
export function useRecorder({
  onRecorded,
  onError,
  silenceMs = 1400,
  noSpeechMs = 8000,
  maxMs = 30000,
}) {
  const [level, setLevel] = useState(0);
  const sessionRef = useRef(null);
  const callbacks = useRef({ onRecorded, onError });
  callbacks.current = { onRecorded, onError };

  const release = useCallback(() => {
    const s = sessionRef.current;
    if (s) {
      if (s.node) s.node.port.onmessage = null;
      try {
        s.source?.disconnect();
        s.node?.disconnect();
        s.mute?.disconnect();
      } catch {
        /* already disconnected */
      }
      s.stream?.getTracks().forEach((t) => t.stop());
      s.audioCtx?.close().catch(() => {});
    }
    sessionRef.current = null;
    setLevel(0);
  }, []);

  const finish = useCallback(
    (reason) => {
      const s = sessionRef.current;
      if (!s || s.finished) return;
      s.finished = true;
      const { chunks, sampleRate } = s;
      release();
      if (reason === "cancel") return;
      if (reason === "no_speech") {
        callbacks.current.onError({
          code: "no_input",
          message: "I didn't hear anything. Please try again.",
        });
        return;
      }
      callbacks.current.onRecorded(chunksToWavBlob(chunks, sampleRate));
    },
    [release]
  );

  const start = useCallback(async () => {
    if (sessionRef.current) return;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!navigator.mediaDevices?.getUserMedia || !AudioCtx || !window.AudioWorkletNode) {
      callbacks.current.onError({
        code: "unsupported",
        message: "This browser cannot record audio. Try a recent Chrome, Edge, Firefox or Safari.",
      });
      return;
    }

    const session = { starting: true, finished: false, cancelled: false, chunks: [], samples: 0, sampleRate: 0 };
    sessionRef.current = session;
    const aborted = () => sessionRef.current !== session || session.cancelled;
    const abandon = (stream, ctx) => {
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close?.().catch(() => {});
      if (sessionRef.current === session) sessionRef.current = null;
    };

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      if (sessionRef.current === session) sessionRef.current = null;
      callbacks.current.onError({ code: "mic_error", message: micErrorMessage(err) });
      return;
    }
    if (aborted()) return abandon(stream);

    let audioCtx;
    try {
      audioCtx = new AudioCtx();
      await audioCtx.audioWorklet.addModule(WORKLET_URL);
      await audioCtx.resume?.();
    } catch {
      abandon(stream, audioCtx);
      callbacks.current.onError({ code: "audio_error", message: "Could not start audio capture in this browser." });
      return;
    }
    if (aborted()) return abandon(stream, audioCtx);

    const source = audioCtx.createMediaStreamSource(stream);
    const node = new AudioWorkletNode(audioCtx, "pcm-capture");
    const mute = audioCtx.createGain(); // keeps the graph running without playing the mic aloud
    mute.gain.value = 0;
    source.connect(node);
    node.connect(mute);
    mute.connect(audioCtx.destination);
    Object.assign(session, { starting: false, stream, audioCtx, source, node, mute, sampleRate: audioCtx.sampleRate });

    let heardSpeech = false;
    let lastVoiceAt = 0;
    let threshold = 0.02;
    const noise = [];

    node.port.onmessage = (event) => {
      if (session.finished) return;
      const samples = event.data;
      session.chunks.push(samples);
      session.samples += samples.length;

      const elapsed = session.samples / audioCtx.sampleRate; // seconds of audio captured
      const rms = rmsOf(samples);
      setLevel(Math.min(1, rms * 6));

      if (elapsed < 0.4) {
        noise.push(rms);
        threshold = Math.min(0.06, Math.max(0.02, average(noise) * 2.5));
        return;
      }
      if (rms > threshold) {
        heardSpeech = true;
        lastVoiceAt = elapsed;
      }
      if (heardSpeech && elapsed - lastVoiceAt > silenceMs / 1000) finish("silence");
      else if (!heardSpeech && elapsed > noSpeechMs / 1000) finish("no_speech");
      else if (elapsed > maxMs / 1000) finish("max");
    };
  }, [finish, maxMs, noSpeechMs, silenceMs]);

  /** Finish now and send what was recorded. */
  const stop = useCallback(() => finish("manual"), [finish]);

  /** Abort and throw the recording away. */
  const cancel = useCallback(() => {
    const s = sessionRef.current;
    if (!s) return;
    s.cancelled = true;
    if (!s.starting) finish("cancel");
  }, [finish]);

  useEffect(() => () => cancel(), [cancel]);

  return { start, stop, cancel, level };
}
