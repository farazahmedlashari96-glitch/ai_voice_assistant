// Thin wrapper around the Django JSON API.
const BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, { code = "error", status = 0 } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function request(path, { method = "GET", json, formData, signal } = {}) {
  let res;
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method,
      signal,
      headers: json ? { "Content-Type": "application/json" } : undefined,
      body: json ? JSON.stringify(json) : formData,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError("Cannot reach the server. Is the Django backend running?", {
      code: "network_error",
    });
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    /* body was not JSON */
  }
  if (!res.ok) {
    const info = data?.error;
    throw new ApiError(info?.message || `Request failed (${res.status}).`, {
      code: info?.code || "http_error",
      status: res.status,
    });
  }
  return data;
}

export const api = {
  health: () => request("/health/"),

  /** Typed message (used for testing without a microphone). */
  sendChat: ({ message, history, signal }) =>
    request("/chat/", { method: "POST", signal, json: { message, history, speak: true } }),

  /** Recorded WAV audio -> transcript + reply + spoken reply. */
  sendVoice: ({ wav, history, signal }) => {
    const form = new FormData();
    form.append("audio", wav, "recording.wav");
    form.append("history", JSON.stringify(history));
    form.append("speak", "true");
    return request("/voice/", { method: "POST", signal, formData: form });
  },
};
