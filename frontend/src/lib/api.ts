import type { ChatTurnResponse } from "@/types/chat";

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

