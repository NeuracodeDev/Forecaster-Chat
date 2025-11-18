export type MessageRole = "user" | "assistant" | "tool";

export interface MessageDTO {
  id: string;
  role: MessageRole;
  content?: string | null;
  raw_payload?: Record<string, unknown> | null;
  sequence_index: number;
  created_at: string;
}

export interface UploadArtifactDTO {
  id: string;
  session_id: string;
  message_id?: string | null;
  original_filename: string;
  stored_path: string;
  mime_type?: string | null;
  size_bytes?: number | null;
  extraction_status: string;
  extraction_result?: Record<string, unknown> | null;
  created_at: string;
}

export interface ChatTurnResponse {
  session_id: string;
  created_new_session: boolean;
  user_message: MessageDTO;
  assistant_message: MessageDTO;
  tool_messages: MessageDTO[];
  uploads: UploadArtifactDTO[];
  forecast_job_id?: string | null;
  chronos_response?: Record<string, unknown> | null;
}

