import type {
  ChatTurnResponse,
  SessionDetailResponse,
  SessionSummaryDTO,
} from "@/types/chat";

const { VITE_API_BASE } = import.meta.env;
const API_BASE: string = typeof VITE_API_BASE === "string" && VITE_API_BASE.length > 0 ? VITE_API_BASE : "/api/v1";

export interface SubmitChatPayload {
  sessionId?: string;
  content?: string;
  files?: File[];
}

export type ChatProgressStep =
  | "structuring"
  | "inference_start"
  | "inference_complete"
  | "preparing_response"
  | "reasoning";

export interface SubmitChatOptions {
  onProgress?: (step: ChatProgressStep) => void;
  onSession?: (event: { sessionId: string; title: string; createdNew: boolean }) => void;
  signal?: AbortSignal;
}

export async function submitChatMessage(
  {
    sessionId,
    content,
    files,
  }: SubmitChatPayload,
  options?: SubmitChatOptions,
): Promise<ChatTurnResponse> {
  const formData = new FormData();
  if (sessionId) {
    formData.append("session_id", sessionId);
  }
  if (content) {
    formData.append("content", content);
  }
  files?.forEach((file) => formData.append("files", file));

  const response = await fetch(`${API_BASE}/chat/message`, {
    method: "POST",
    body: formData,
    signal: options?.signal,
  });

  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || "Failed to submit chat message.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload: ChatTurnResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const segments = buffer.split("\n\n");
    buffer = segments.pop() ?? "";

    for (const segment of segments) {
      const trimmed = segment.trim();
      if (!trimmed.startsWith("data:")) {
        continue;
      }
      const jsonPayload = trimmed.slice(5).trim();
      if (!jsonPayload) {
        continue;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(jsonPayload);
      } catch {
        continue;
      }
      if (!parsed || typeof parsed !== "object") {
        continue;
      }
      const event = parsed as Record<string, unknown>;
      if (event.type === "progress" && typeof event.step === "string") {
        options?.onProgress?.(event.step as ChatProgressStep);
      } else if (event.type === "session" && typeof event.session_id === "string") {
        options?.onSession?.({
          sessionId: event.session_id,
          title: typeof event.title === "string" ? event.title : "",
          createdNew: Boolean(event.created_new),
        });
      } else if (event.type === "result" && event.payload) {
        finalPayload = event.payload as ChatTurnResponse;
      }
    }
  }

  if (!finalPayload) {
    throw new Error("Response stream ended without result.");
  }

  return finalPayload;
}

export async function fetchSessions(): Promise<SessionSummaryDTO[]> {
  const response = await fetch(`${API_BASE}/chat/sessions`, {
    method: "GET",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to fetch sessions.");
  }
  return (await response.json()) as SessionSummaryDTO[];
}

export async function fetchSessionDetail(sessionId: string): Promise<SessionDetailResponse> {
  const response = await fetch(`${API_BASE}/chat/session/${sessionId}`, {
    method: "GET",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to fetch session.");
  }
  return (await response.json()) as SessionDetailResponse;
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/session/${sessionId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to delete session.");
  }
}

