import { useCallback, useRef, useState } from "react";
import { base64ToBlob } from "../audio/base64.js";

/**
 * Functional requirement 5 - play the assistant's spoken reply.
 * Plays the server's audio (Groq TTS, base64 WAV) or, if that failed, the browser's
 * built-in speech synthesis. Every play* call returns a promise that resolves true
 * when playback finished, false if it failed or was stopped.
 */
export function useSpeaker() {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const audioRef = useRef(null);
  const urlRef = useRef(null);
  const pendingRef = useRef(null);

  const teardown = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }, []);

  const stop = useCallback(() => {
    const resolve = pendingRef.current;
    pendingRef.current = null;
    teardown();
    resolve?.(false);
  }, [teardown]);

  const playBase64 = useCallback(
    (b64, mime = "audio/wav") => {
      stop();
      return new Promise((resolve) => {
        const url = URL.createObjectURL(base64ToBlob(b64, mime));
        const audio = new Audio(url);
        urlRef.current = url;
        audioRef.current = audio;
        pendingRef.current = resolve;

        const finish = (ok) => {
          if (pendingRef.current !== resolve) return;
          pendingRef.current = null;
          teardown();
          resolve(ok);
        };
        audio.onended = () => finish(true);
        audio.onerror = () => finish(false);
        setIsSpeaking(true);
        audio.play().catch(() => finish(false));
      });
    },
    [stop, teardown]
  );

  const speakText = useCallback(
    (text) => {
      stop();
      return new Promise((resolve) => {
        if (!("speechSynthesis" in window)) {
          resolve(false);
          return;
        }
        const utterance = new SpeechSynthesisUtterance(text);
        pendingRef.current = resolve;
        const finish = (ok) => {
          if (pendingRef.current !== resolve) return;
          pendingRef.current = null;
          teardown();
          resolve(ok);
        };
        utterance.onend = () => finish(true);
        utterance.onerror = () => finish(false);
        setIsSpeaking(true);
        window.speechSynthesis.speak(utterance);
      });
    },
    [stop, teardown]
  );

  return { isSpeaking, playBase64, speakText, stop };
}
