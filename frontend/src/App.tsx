import React, { useMemo, useState } from "react";
import { AlertCircle } from "lucide-react";

import "./App.css";
import { ChatComposer } from "@/components/chat/chat-composer";
import { MessageList, type ChatMessage } from "@/components/chat/message-list";
import { Sidebar, type ChatSessionSummary } from "@/components/chat/sidebar";
import { Separator } from "@/components/ui/separator";
import { submitChatMessage } from "@/lib/api";
import type { ChatTurnResponse, MessageDTO, UploadArtifactDTO } from "@/types/chat";

interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  uploads: UploadArtifactDTO[];
  chronosResponse?: Record<string, unknown> | null;
  forecastJobId?: string | null;
  lastUpdated: string;
}

const App: React.FC = () => {
  const [sessions, setSessions] = useState<Record<string, ChatSession>>({});
  const [sessionOrder, setSessionOrder] = useState<string[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  const [messageInput, setMessageInput] = useState("");
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const sessionSummaries: ChatSessionSummary[] = useMemo(
    () =>
      sessionOrder.map((id) => {
        const session = sessions[id];
        return {
          id,
          title: session?.title ?? "Untitled conversation",
          lastUpdated: session?.lastUpdated ?? new Date().toISOString(),
        };
      }),
    [sessionOrder, sessions],
  );

  const activeSession = selectedSessionId ? sessions[selectedSessionId] : null;
  const activeMessages = activeSession?.messages ?? [];

  const handleSelectSession = (sessionId: string | null) => {
    setSelectedSessionId(sessionId);
    setMessageInput("");
    setPendingFiles([]);
    setError(null);
  };

  const handleCreateSession = () => {
    handleSelectSession(null);
  };

  const handleFilesChange = (files: File[]) => {
    const imageCount = files.filter((file) => file.type.startsWith("image/")).length;
    if (imageCount > 20) {
      setError("Please select at most 20 images per message.");
      return;
    }
    setError(null);
    setPendingFiles(files);
  };

  const handleSubmit = async () => {
    if (!messageInput.trim() && pendingFiles.length === 0) {
      setError("Add a prompt or at least one file before sending.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await submitChatMessage({
        sessionId: selectedSessionId ?? undefined,
        content: messageInput.trim() || undefined,
        files: pendingFiles,
      });
      ingestResponse(response);
      setMessageInput("");
      setPendingFiles([]);
    } catch (cause) {
      const message =
        cause instanceof Error ? cause.message : "Something went wrong while contacting the API.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const ingestResponse = (response: ChatTurnResponse) => {
    const sessionId = response.session_id;
    const sessionTitle = deriveSessionTitle(
      sessions[sessionId]?.title,
      response.user_message.content ?? undefined,
      response.uploads,
    );

    const messageBundle: ChatMessage[] = [
      toChatMessage(response.user_message),
      ...response.tool_messages.map(toChatMessage),
      toChatMessage(response.assistant_message),
    ];

    setSessions((prev) => {
      const existing = prev[sessionId];
      const nextMessages = existing ? [...existing.messages, ...messageBundle] : messageBundle;
      const nowIso = new Date().toISOString();

      return {
        ...prev,
        [sessionId]: {
          id: sessionId,
          title: sessionTitle,
          messages: nextMessages,
          uploads: response.uploads,
          chronosResponse: response.chronos_response ?? existing?.chronosResponse ?? null,
          forecastJobId: response.forecast_job_id ?? existing?.forecastJobId ?? null,
          lastUpdated: nowIso,
        },
      };
    });

    setSessionOrder((prev) => {
      const filtered = prev.filter((id) => id !== sessionId);
      return [sessionId, ...filtered];
    });

    setSelectedSessionId(sessionId);
  };

  return (
    <div className="flex h-screen w-full bg-background text-foreground">
      <Sidebar
        sessions={sessionSummaries}
        selectedSessionId={selectedSessionId}
        onSelectSession={handleSelectSession}
        onCreateSession={handleCreateSession}
      />
      <main className="flex h-full flex-1 flex-col">
        <div className="flex-1">
          {activeSession ? (
            <MessageList messages={activeMessages} isLoading={isSubmitting} />
          ) : (
            <EmptyState />
          )}
        </div>
        {activeSession?.uploads?.length ? (
          <>
            <Separator />
            <UploadInspector uploads={activeSession.uploads} />
          </>
        ) : null}
        <Separator />
        <ChatComposer
          message={messageInput}
          onMessageChange={setMessageInput}
          files={pendingFiles}
          onFilesChange={handleFilesChange}
          onSubmit={handleSubmit}
          isSubmitting={isSubmitting}
        />
        {error && (
          <div className="flex items-center gap-2 border-t border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        )}
      </main>
    </div>
  );
};

const EmptyState: React.FC = () => (
  <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-muted-foreground">
    <h2 className="text-xl font-semibold text-foreground">Start a new Chronos conversation</h2>
    <p className="max-w-md text-sm leading-relaxed">
      Upload a dataset, chart, or PDF and Chronos will normalize it, run forecasts, and craft a rich
      explanation for you. You can also chat without files to discuss existing forecasts.
    </p>
  </div>
);

const UploadInspector: React.FC<{ uploads: UploadArtifactDTO[] }> = ({ uploads }) => (
  <div className="grid gap-3 p-4">
    <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
      Uploaded files
    </h3>
    <div className="grid gap-2 text-sm">
      {uploads.map((upload) => (
        <div
          key={upload.id}
          className="flex items-center justify-between rounded-md border border-border bg-muted/40 px-3 py-2"
        >
          <div className="flex flex-1 flex-col">
            <span className="font-medium text-foreground">{upload.original_filename}</span>
            <span className="text-xs uppercase tracking-wide text-muted-foreground">
              {upload.extraction_status}
            </span>
          </div>
          {typeof upload.size_bytes === "number" && (
            <span className="text-xs text-muted-foreground">
              {(upload.size_bytes / 1024).toFixed(1)} KB
            </span>
          )}
        </div>
      ))}
    </div>
  </div>
);

const toChatMessage = (dto: MessageDTO): ChatMessage => ({
  id: dto.id,
  role: dto.role,
  content: dto.content ?? "",
  rawPayload: dto.raw_payload ?? undefined,
  createdAt: dto.created_at,
});

const deriveSessionTitle = (
  existingTitle: string | undefined,
  latestContent: string | undefined,
  uploads: UploadArtifactDTO[],
): string => {
  if (existingTitle) {
    return existingTitle;
  }
  if (latestContent) {
    const trimmed = latestContent.trim();
    if (trimmed.length > 0) {
      return trimmed.slice(0, 48) + (trimmed.length > 48 ? "…" : "");
    }
  }
  if (uploads.length > 0) {
    return `Uploaded ${uploads.length} file${uploads.length > 1 ? "s" : ""}`;
  }
  return "New conversation";
};

export default App;
