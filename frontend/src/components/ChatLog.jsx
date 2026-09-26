import { useEffect, useRef } from "react";
import Message from "./Message.jsx";

const STEPS = [
  "You speak (microphone → WAV recording)",
  "Speech-to-Text turns it into text",
  "The text is sent to the LLM API",
  "The reply is converted to speech (Text-to-Speech)",
  "You hear the audio and see the text",
];

export default function ChatLog({ messages, status, targetMs }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, status]);

  if (messages.length === 0) {
    return (
      <section className="log log--empty">
        <p className="log__lead">Press <strong>Start talking</strong> and ask something.</p>
        <ol className="steps">
          {STEPS.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>
    );
  }

  return (
    <section className="log" aria-live="polite">
      {messages.map((m) => (
        <Message key={m.id} message={m} targetMs={targetMs} />
      ))}
      {status === "thinking" && (
        <div className="msg msg--bot">
          <span className="msg__label">AI assistant</span>
          <div className="msg__bubble typing" aria-label="The assistant is thinking">
            <span />
            <span />
            <span />
          </div>
        </div>
      )}
      <div ref={endRef} />
    </section>
  );
}
