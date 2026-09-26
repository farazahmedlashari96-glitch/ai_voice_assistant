const STATUS_TEXT = {
  idle: "Ready",
  listening: "Listening… speak, then pause",
  thinking: "Transcribing and thinking…",
  speaking: "Speaking…",
};

export default function Controls({
  status,
  level,
  continuous,
  onToggleContinuous,
  onMic,
  onStop,
  draft,
  setDraft,
  onSend,
}) {
  const listening = status === "listening";
  const working = status === "thinking" || status === "speaking";

  const submit = (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (text && !working && !listening) onSend(text);
  };

  return (
    <footer className="controls">
      <div className="controls__top">
        <span className={`status status--${status}`}>{STATUS_TEXT[status]}</span>
        <label className="toggle" title="After each reply the microphone opens again, until you say 'exit' or 'stop'.">
          <input type="checkbox" checked={continuous} onChange={(e) => onToggleContinuous(e.target.checked)} />
          <span>Continuous conversation</span>
        </label>
      </div>

      {listening && (
        <div className="meter" aria-hidden="true">
          <span style={{ transform: `scaleX(${Math.max(0.03, level)})` }} />
        </div>
      )}

      {working ? (
        <button type="button" className="mic mic--stop" onClick={onStop}>
          ⏹ Stop
        </button>
      ) : (
        <button type="button" className={`mic ${listening ? "mic--live" : ""}`} onClick={onMic}>
          {listening ? "✔ Done" : "🎤 Start talking"}
        </button>
      )}

      <form className="typing-form" onSubmit={submit}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Or type a message (handy for testing)"
          disabled={listening}
          maxLength={1000}
          aria-label="Message"
        />
        <button type="submit" disabled={!draft.trim() || working || listening}>
          Send
        </button>
      </form>
      <p className="hint">Say or type “exit” or “stop” to end the conversation.</p>
    </footer>
  );
}
