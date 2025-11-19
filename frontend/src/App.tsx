import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle } from "lucide-react";

import "./App.css";
import { ChatComposer } from "@/components/chat/chat-composer";
import { MessageList, type ChatMessage } from "@/components/chat/message-list";
import { Sidebar, type ChatSessionSummary } from "@/components/chat/sidebar";
import { fetchSessionDetail, fetchSessions, submitChatMessage } from "@/lib/api";
import type {
  ChatTurnResponse,
  MessageDTO,
  SessionSummaryDTO,
  UploadArtifactDTO,
} from "@/types/chat";

interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  uploads: UploadArtifactDTO[];
  chronosResponse?: Record<string, unknown> | null;
  forecastJobId?: string | null;
  lastUpdated: string;
  createdAt: string;
  isHydrated: boolean;
}

const App: React.FC = () => {
  const [sessions, setSessions] = useState<Record<string, ChatSession>>({});
  const [sessionOrder, setSessionOrder] = useState<string[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [hydratingSessions, setHydratingSessions] = useState<Record<string, boolean>>({});
  const [sessionsLoading, setSessionsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const loadSessions = async () => {
      setSessionsLoading(true);
      try {
        const summaries = await fetchSessions();
        if (cancelled) {
          return;
        }
        setSessions((prev) => {
          const next = { ...prev };
          summaries.forEach((summary) => {
            const existing = prev[summary.id];
            next[summary.id] = {
              id: summary.id,
              title: summary.title ?? existing?.title ?? "Untitled conversation",
              messages: existing?.messages ?? [],
              uploads: existing?.uploads ?? [],
              chronosResponse: existing?.chronosResponse ?? null,
              forecastJobId: existing?.forecastJobId ?? null,
              lastUpdated: summary.last_message_at ?? summary.updated_at ?? summary.created_at,
              createdAt: summary.created_at,
              isHydrated: existing?.isHydrated ?? false,
            };
          });
          return next;
        });
        setSessionOrder(summaries.map((summary) => summary.id));
        if (summaries.length > 0) {
          setSelectedSessionId((current) => current ?? summaries[0].id);
        }
      } catch (cause) {
        if (!cancelled) {
          const message = cause instanceof Error ? cause.message : "Failed to load sessions.";
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setSessionsLoading(false);
        }
      }
    };

    void loadSessions();
    return () => {
      cancelled = true;
    };
  }, []);

  const hydrateSession = useCallback(
    async (sessionId: string) => {
      const sessionRecord = sessions[sessionId];
      if (!sessionRecord || sessionRecord.isHydrated || hydratingSessions[sessionId]) {
        return;
      }
      setHydratingSessions((prev) => ({ ...prev, [sessionId]: true }));
      try {
        const detail = await fetchSessionDetail(sessionId);
        setSessions((prev) => {
          const existing = prev[sessionId];
          if (!existing) {
            return prev;
          }
          return {
            ...prev,
            [sessionId]: {
              ...existing,
              title: detail.session_title ?? existing.title,
              messages: detail.messages.map(toChatMessage),
              uploads: detail.uploads,
              lastUpdated: detail.updated_at ?? existing.lastUpdated,
              createdAt: detail.created_at ?? existing.createdAt,
              isHydrated: true,
            },
          };
        });
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : "Failed to load session.";
        setError(message);
      } finally {
        setHydratingSessions((prev) => {
          const next = { ...prev };
          delete next[sessionId];
          return next;
        });
      }
    },
    [hydratingSessions, sessions],
  );

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
          lastUpdated: session?.lastUpdated ?? session?.createdAt ?? new Date().toISOString(),
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
    if (sessionId) {
      void hydrateSession(sessionId);
    }
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

    const messageBundle: ChatMessage[] = [
      toChatMessage(response.user_message),
      ...response.tool_messages.map(toChatMessage),
      toChatMessage(response.assistant_message),
    ];

    setSessions((prev) => {
      const existing = prev[sessionId];
      const fallbackTitle = deriveSessionTitle(response.user_message.content ?? undefined, response.uploads);
      const sessionTitle = response.session_title ?? existing?.title ?? fallbackTitle;
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
          createdAt: existing?.createdAt ?? nowIso,
          isHydrated: true,
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
    <div className="flex h-screen w-screen overflow-hidden bg-muted text-foreground">
      <Sidebar
        sessions={sessionSummaries}
        selectedSessionId={selectedSessionId}
        onSelectSession={handleSelectSession}
        onCreateSession={handleCreateSession}
      />
      <main className="flex h-full flex-1 flex-col bg-background">
        <div className="flex-1 overflow-hidden px-12 py-10">
          <div className="flex h-full w-full flex-col">
            {activeSession ? (
              <MessageList
                messages={activeMessages}
                isLoading={isSubmitting || !!(selectedSessionId && hydratingSessions[selectedSessionId])}
              />
            ) : sessionsLoading ? (
              <LoadingState />
            ) : (
              <EmptyState />
            )}
          </div>
        </div>
        {activeSession?.isHydrated && activeSession.uploads?.length ? (
          <UploadInspector uploads={activeSession.uploads} />
        ) : null}
        <ChatComposer
          message={messageInput}
          onMessageChange={setMessageInput}
          files={pendingFiles}
          onFilesChange={handleFilesChange}
          onSubmit={handleSubmit}
          isSubmitting={isSubmitting}
        />
        {error && (
          <div className="flex items-center gap-2 border-t border-destructive/50 bg-destructive/10 px-10 py-4 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        )}
      </main>
    </div>
  );
};

const LoadingState: React.FC = () => (
  <div className="flex h-full flex-col items-center justify-center gap-4 text-muted-foreground">
    <span className="text-sm uppercase tracking-[0.3em]">Loading sessions</span>
    <span className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-transparent" />
  </div>
);

const EmptyState: React.FC = () => (
  <div className="flex h-full flex-col justify-center gap-12">
    <div className="space-y-4 text-center">
      <p className="text-[11px] uppercase tracking-[0.4em] text-muted-foreground">Forecaster</p>
      <h2 className="text-4xl font-semibold text-foreground">Start a new Chronos conversation</h2>
      <p className="mx-auto max-w-3xl text-base leading-relaxed text-muted-foreground">
        Upload CSVs, PDFs, or charts and Chronos+LLM will normalize the data, run forecasts, and translate the full
        quantile response into polished insights. You can also chat without files to revisit previous jobs.
      </p>
    </div>
    <div className="grid gap-4 md:grid-cols-3">
      {[
        {
          title: "Upload files",
          body: "CSV, TSV, JSON, TXT, PDF, and up to 20 images per turn.",
        },
        {
          title: "Chronos forecast",
          body: "Auto-detects uni or multivariate structure with covariates.",
        },
        {
          title: "Explain results",
          body: "LLM summarizes quantiles and highlights anomalies for you.",
        },
      ].map((card, idx) => (
        <div
          key={card.title}
          className="rounded-xl border border-border/60 bg-card px-5 py-5 text-left shadow-sm transition hover:border-border/80"
        >
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground/70">
            {String(idx + 1).padStart(2, "0")}
          </span>
          <h3 className="mt-2 text-base font-semibold text-foreground">{card.title}</h3>
          <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">{card.body}</p>
        </div>
      ))}
    </div>
  </div>
);

const UploadInspector: React.FC<{ uploads: UploadArtifactDTO[] }> = ({ uploads }) => (
  <div className="border-t border-border bg-panel px-12 py-6">
    <div className="flex items-center justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Uploaded files</p>
        <p className="text-xs text-muted-foreground">Metadata stored, originals discarded.</p>
      </div>
      <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
        {uploads.length} file{uploads.length === 1 ? "" : "s"}
      </span>
    </div>
    <div className="mt-4 grid gap-3 md:grid-cols-2">
      {uploads.map((upload) => (
        <div
          key={upload.id}
          className="flex items-center justify-between rounded-2xl border border-border bg-card px-4 py-3 text-sm shadow-sm"
        >
          <div>
            <p className="font-medium text-foreground">{upload.original_filename}</p>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{upload.extraction_status}</p>
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
  latestContent: string | undefined,
  uploads: UploadArtifactDTO[],
): string => {
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
