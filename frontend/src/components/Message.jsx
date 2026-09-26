import { useEffect, useState } from "react";
import { base64ToBlob } from "../audio/base64.js";

function timingDetails(t = {}) {
  const parts = [
    ["Speech-to-Text", t.stt_ms],
    ["LLM", t.llm_ms],
    ["Text-to-Speech", t.tts_ms],
  ]
    .filter(([, ms]) => ms != null)
    .map(([label, ms]) => `${label} ${(ms / 1000).toFixed(1)} s`);
  return parts.join(" · ");
}

/** One chat entry: the user's text, or the AI's text + audio playback + response time. */
export default function Message({ message, targetMs }) {
  const isUser = message.role === "user";
  const [audioUrl, setAudioUrl] = useState(null);

  useEffect(() => {
    if (!message.audio) {
      setAudioUrl(null);
      return undefined;
    }
    const url = URL.createObjectURL(base64ToBlob(message.audio, message.audioMime));
    setAudioUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [message.audio, message.audioMime]);

  const total = message.timings?.total_ms;

  return (
    <div className={`msg msg--${isUser ? "user" : "bot"} ${message.pending ? "msg--pending" : ""}`}>
      <span className="msg__label">{isUser ? "You" : "AI assistant"}</span>
      {/* Plain text (never HTML), so model output cannot inject markup. */}
      <div className="msg__bubble">
        <p>{message.content}</p>
      </div>
      {audioUrl && <audio className="msg__audio" controls preload="none" src={audioUrl} aria-label="Reply audio" />}
      {total != null && (
        <span className={`msg__time ${total <= targetMs ? "is-fast" : "is-slow"}`} title={timingDetails(message.timings)}>
          ⏱ {(total / 1000).toFixed(1)} s
        </span>
      )}
    </div>
  );
}
