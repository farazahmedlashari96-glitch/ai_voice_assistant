import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App.jsx";

const REPLY = "Paris is the capital of France.";

const turn = (extra = {}) => ({
  user_text: "What is the capital of France",
  reply: REPLY,
  exit: false,
  audio: null,
  audio_mime: null,
  tts_error: null,
  timings: { llm_ms: 400, tts_ms: 900, total_ms: 1300 },
  ...extra,
});

function json(body, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

function installFetch(chatResponse) {
  const fetchMock = vi.fn((url, init) => {
    if (url.endsWith("/api/health/")) {
      return json({
        status: "ok",
        groq_configured: true,
        response_time_target_ms: 5000,
        models: { llm: "llama", stt: "whisper", tts: "orpheus" },
      });
    }
    if (url.endsWith("/api/chat/")) return chatResponse(init);
    return json({ error: { code: "not_found", message: "nope" } }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const chatCalls = (fetchMock) =>
  fetchMock.mock.calls.filter(([url]) => url.endsWith("/api/chat/")).map(([, init]) => JSON.parse(init.body));

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function type(text) {
  fireEvent.change(screen.getByLabelText("Message"), { target: { value: text } });
  fireEvent.click(screen.getByText("Send"));
}

describe("AI Voice Assistant", () => {
  it("shows the title, the workflow steps and the backend model", async () => {
    installFetch(() => json(turn()));
    render(<App />);
    expect(screen.getByRole("heading", { name: "AI Voice Assistant" })).toBeTruthy();
    expect(screen.getByText(/Speech-to-Text turns it into text/)).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/Groq · llama/)).toBeTruthy());
  });

  it("shows the user's text, the AI's text and the response time", async () => {
    const fetchMock = installFetch(() => json(turn()));
    render(<App />);
    type("What is the capital of France");

    await waitFor(() => expect(screen.getByText(REPLY)).toBeTruthy());
    expect(screen.getByText("What is the capital of France")).toBeTruthy();
    expect(screen.getByText(/⏱ 1\.3 s/)).toBeTruthy();
    expect(chatCalls(fetchMock)[0]).toMatchObject({ message: "What is the capital of France", history: [], speak: true });
    await waitFor(() => expect(screen.getByText("Ready")).toBeTruthy());
  });

  it("remembers the conversation by sending the history with the next message", async () => {
    const fetchMock = installFetch(() => json(turn()));
    render(<App />);
    type("first question");
    await waitFor(() => expect(screen.getByText(REPLY)).toBeTruthy());
    await waitFor(() => expect(screen.getByText("Ready")).toBeTruthy());
    type("second question");
    await waitFor(() => expect(chatCalls(fetchMock)).toHaveLength(2));

    expect(chatCalls(fetchMock)[1].history).toEqual([
      { role: "user", content: "What is the capital of France" },
      { role: "assistant", content: REPLY },
    ]);
  });

  it("plays the reply audio, shows a player, and goes back to idle when it ends", async () => {
    const played = [];
    class FakeAudio {
      play() { played.push(true); setTimeout(() => this.onended?.(), 10); return Promise.resolve(); }
      pause() {}
    }
    vi.stubGlobal("Audio", FakeAudio);
    installFetch(() => json(turn({ audio: btoa("RIFFdata"), audio_mime: "audio/wav" })));
    const { container } = render(<App />);
    type("hello");

    await waitFor(() => expect(screen.getByText(REPLY)).toBeTruthy());
    await waitFor(() => expect(container.querySelector("audio[controls]")).toBeTruthy());
    await waitFor(() => expect(played.length).toBe(1));
    await waitFor(() => expect(screen.getByText("Ready")).toBeTruthy());
  });

  it("shows API errors and puts the text back in the input", async () => {
    installFetch(() => json({ error: { code: "upstream_error", message: "The AI service failed." } }, 502));
    render(<App />);
    type("hello there");

    await waitFor(() => expect(screen.getByText("The AI service failed.")).toBeTruthy());
    expect(screen.getByLabelText("Message").value).toBe("hello there");
    expect(screen.getByText("Ready")).toBeTruthy();
  });

  it("ends continuous conversation when the assistant reports an exit command", async () => {
    installFetch(() => json(turn({ user_text: "Exit", reply: "Goodbye! Have a great day.", exit: true })));
    render(<App />);
    expect(screen.getByLabelText("Continuous conversation").checked).toBe(true);
    type("exit");

    await waitFor(() => expect(screen.getByText("Goodbye! Have a great day.")).toBeTruthy());
    expect(screen.getByLabelText("Continuous conversation").checked).toBe(false);
  });

  it("reports when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    render(<App />);
    await waitFor(() => expect(screen.getByText(/Can't reach the backend/)).toBeTruthy());
  });
});
