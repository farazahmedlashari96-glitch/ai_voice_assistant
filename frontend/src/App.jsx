import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { useRecorder } from "./hooks/useRecorder.js";
import { useSpeaker } from "./hooks/useSpeaker.js";
import ChatLog from "./components/ChatLog.jsx";
import Controls from "./components/Controls.jsx";

const MAX_SILENT_RETRIES = 3; // continuous mode gives up after this many empty recordings in a row
const HISTORY_LIMIT = 12; // messages of context sent with each request (conversation memory)
const DEFAULT_TARGET_MS = 5000; // project requirement: respond within 2-5 seconds

let messageCounter = 0;
const newId = () => `m${++messageCounter}`;

export default function App() {
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | listening | thinking | speaking
  const [notice, setNotice] = useState(null); // { type: "error" | "info", text }
  const [draft, setDraft] = useState("");
  const [continuous, setContinuous] = useState(true);
  const [backend, setBackend] = useState(null);

  // Refs let long-running async flows read the latest values without stale closures.
  const runRef = useRef(0); // incremented to invalidate the flow that is currently running
  const abortRef = useRef(null);
  const messagesRef = useRef([]);
  const continuousRef = useRef(true);
  const silentStreakRef = useRef(0);
  const fnsRef = useRef({});

  const { playBase64, speakText, stop: stopSpeaking } = useSpeaker();
  const {
    start: startRecording,
    stop: stopRecording,
    cancel: cancelRecording,
    level,
  } = useRecorder({
    onRecorded: (wav) => fnsRef.current.submitVoice(wav),
    onError: (err) => fnsRef.current.recorderError(err),
  });

  // ------------------------------------------------------------ small helpers
  const commit = useCallback((updater) => {
    setMessages((prev) => {
      const next = updater(prev);
      messagesRef.current = next;
      return next;
    });
  }, []);

  const updateContinuous = useCallback((value) => {
    continuousRef.current = value;
    setContinuous(value);
  }, []);

  /** Conversation memory: the recent messages the LLM should see. */
  const historyForServer = () =>
    messagesRef.current
      .filter((m) => !m.pending)
      .map(({ role, content }) => ({ role, content }))
      .slice(-HISTORY_LIMIT);

  // ------------------------------------------------------------ listening
  const startListening = useCallback(async () => {
    stopSpeaking();
    setNotice(null);
    setStatus("listening");
    await startRecording();
  }, [startRecording, stopSpeaking]);

  /** Error handling: no input / unclear audio. In continuous mode, try again a few times. */
  const handleSilence = useCallback(
    (message) => {
      setStatus("idle");
      silentStreakRef.current += 1;
      if (!continuousRef.current) {
        setNotice({ type: "error", text: message });
      } else if (silentStreakRef.current < MAX_SILENT_RETRIES) {
        setNotice({ type: "info", text: message });
        setTimeout(() => {
          if (continuousRef.current) fnsRef.current.startListening();
        }, 600);
      } else {
        updateContinuous(false);
        setNotice({
          type: "info",
          text: "Conversation paused because I didn't hear anything. Press Start talking to continue.",
        });
      }
    },
    [updateContinuous]
  );

  const recorderError = useCallback(
    (err) => {
      if (err.code === "no_input") {
        handleSilence(err.message);
        return;
      }
      setStatus("idle");
      setNotice({ type: "error", text: err.message });
    },
    [handleSilence]
  );

  // ------------------------------------------------------------ one conversation turn
  const runTurn = useCallback(
    async ({ pendingText, restoreDraft, request }) => {
      const runId = ++runRef.current;
      const controller = new AbortController();
      abortRef.current = controller;
      const history = historyForServer();
      const pendingId = newId();

      stopSpeaking();
      setNotice(null);
      setStatus("thinking");
      commit((prev) => [...prev, { id: pendingId, role: "user", content: pendingText, pending: true }]);

      try {
        const turn = await request({ signal: controller.signal, history });
        if (runRef.current !== runId) return; // stopped or superseded meanwhile
        silentStreakRef.current = 0;

        commit((prev) => [
          ...prev.filter((m) => m.id !== pendingId),
          { id: newId(), role: "user", content: turn.user_text },
          {
            id: newId(),
            role: "assistant",
            content: turn.reply,
            audio: turn.audio,
            audioMime: turn.audio_mime,
            timings: turn.timings,
          },
        ]);
        if (turn.exit) updateContinuous(false); // "exit" / "stop" ends the conversation loop

        if (turn.tts_error) {
          setNotice({
            type: "info",
            text: `The AI voice is unavailable, so your browser's voice is used instead. (${turn.tts_error})`,
          });
        }
        setStatus("speaking");
        const played = turn.audio
          ? await playBase64(turn.audio, turn.audio_mime)
          : await speakText(turn.reply);
        if (!played && runRef.current === runId) {
          setNotice({ type: "info", text: "Couldn't play the audio automatically. Use the player under the reply." });
        }

        if (runRef.current !== runId) return;
        setStatus("idle");
        if (continuousRef.current && !turn.exit) fnsRef.current.startListening();
      } catch (err) {
        if (err.name === "AbortError" || runRef.current !== runId) return;
        commit((prev) => prev.filter((m) => m.id !== pendingId));
        if (restoreDraft) setDraft(restoreDraft);
        if (err.code === "no_input" || err.code === "unclear_audio") {
          handleSilence(err.message);
          return;
        }
        setStatus("idle");
        setNotice({ type: "error", text: err.message || "Something went wrong." });
      }
    },
    [commit, handleSilence, playBase64, speakText, stopSpeaking, updateContinuous]
  );

  const sendText = useCallback(
    (text) => {
      setDraft("");
      return runTurn({
        pendingText: text,
        restoreDraft: text,
        request: ({ signal, history }) => api.sendChat({ message: text, history, signal }),
      });
    },
    [runTurn]
  );

  const submitVoice = useCallback(
    (wav) =>
      runTurn({
        pendingText: "Transcribing…",
        request: ({ signal, history }) => api.sendVoice({ wav, history, signal }),
      }),
    [runTurn]
  );

  // ------------------------------------------------------------ controls
  const stopAll = useCallback(() => {
    runRef.current += 1; // invalidates any turn in flight
    abortRef.current?.abort();
    stopSpeaking();
    cancelRecording();
    updateContinuous(false);
    commit((prev) => prev.filter((m) => !m.pending));
    setStatus("idle");
  }, [cancelRecording, commit, stopSpeaking, updateContinuous]);

  const onMic = useCallback(() => {
    if (status === "listening") stopRecording();
    else {
      silentStreakRef.current = 0;
      startListening();
    }
  }, [startListening, status, stopRecording]);

  const onToggleContinuous = useCallback(
    (value) => {
      updateContinuous(value);
      silentStreakRef.current = 0;
    },
    [updateContinuous]
  );

  fnsRef.current = { startListening, submitVoice, recorderError };

  // ------------------------------------------------------------ effects
  useEffect(() => {
    api.health().then(setBackend).catch(() => setBackend({ status: "down" }));
  }, []);

  // ------------------------------------------------------------ render
  const backendDown = backend?.status === "down";
  const needsKey = backend && !backendDown && backend.groq_configured === false;

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>AI Voice Assistant</h1>
          <p className="subtitle">Speech-to-Text · LLM API · Text-to-Speech</p>
        </div>
        {backend?.models && (
          <span className="pill" title={`STT ${backend.models.stt} · TTS ${backend.models.tts}`}>
            Groq · {backend.models.llm}
          </span>
        )}
      </header>

      {backendDown && (
        <div className="banner banner--error">
          Can't reach the backend. Start it with <code>python manage.py runserver</code> in the backend folder.
        </div>
      )}
      {needsKey && (
        <div className="banner banner--error">
          The backend has no <code>GROQ_API_KEY</code>. Add it to <code>backend/.env</code> and restart Django.
        </div>
      )}

      <ChatLog
        messages={messages}
        status={status}
        targetMs={backend?.response_time_target_ms ?? DEFAULT_TARGET_MS}
      />

      {notice && (
        <div className={`notice notice--${notice.type}`} role="status">
          <span>{notice.text}</span>
          <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}

      <Controls
        status={status}
        level={level}
        continuous={continuous}
        onToggleContinuous={onToggleContinuous}
        onMic={onMic}
        onStop={stopAll}
        draft={draft}
        setDraft={setDraft}
        onSend={sendText}
      />
    </div>
  );
}
