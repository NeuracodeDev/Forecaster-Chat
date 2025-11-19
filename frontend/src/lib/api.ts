import type {
  ChatTurnResponse,
  SessionDetailResponse,
  SessionSummaryDTO,
} from "@/types/chat";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export interface SubmitChatPayload {
  sessionId?: string;
  content?: string;
  files?: File[];
}

export async function submitChatMessage({
  sessionId,
  content,
  files,
}: SubmitChatPayload): Promise<ChatTurnResponse> {
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
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to submit chat message.");
  }

  return response.json();
}

export async function fetchSessions(): Promise<SessionSummaryDTO[]> {
  const response = await fetch(`${API_BASE}/chat/sessions`, {
    method: "GET",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to fetch sessions.");
  }
  return response.json();
}

export async function fetchSessionDetail(sessionId: string): Promise<SessionDetailResponse> {
  const response = await fetch(`${API_BASE}/chat/session/${sessionId}`, {
    method: "GET",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to fetch session.");
  }
  return response.json();
}

