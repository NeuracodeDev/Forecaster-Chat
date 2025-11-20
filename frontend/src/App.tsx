import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle } from "lucide-react";

import "./App.css";
import { ChatComposer } from "@/components/chat/chat-composer";
import { MessageList, type ChatMessage } from "@/components/chat/message-list";
import { Sidebar, type ChatSessionSummary } from "@/components/chat/sidebar";
import { deleteSession as deleteSessionRequest, fetchSessionDetail, fetchSessions, submitChatMessage } from "@/lib/api";
import type { ChatTurnResponse, MessageDTO, UploadArtifactDTO } from "@/types/chat";

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
  const [deletingSessions, setDeletingSessions] = useState<Record<string, boolean>>({});

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
              messages: detail.messages.map((msg) => toChatMessage(msg, detail.uploads)),
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

  const handleDeleteSession = async (sessionId: string) => {
    if (!sessionId) {
      return;
    }
    if (!window.confirm("Delete this conversation permanently? This cannot be undone.")) {
      return;
    }
    setDeletingSessions((prev) => ({ ...prev, [sessionId]: true }));
    setError(null);
    try {
      await deleteSessionRequest(sessionId);
      setSessions((prev) => {
        const next = { ...prev };
        delete next[sessionId];
        return next;
      });
      setSessionOrder((prev) => {
        const filtered = prev.filter((id) => id !== sessionId);
        if (selectedSessionId === sessionId) {
          setSelectedSessionId(filtered[0] ?? null);
          setMessageInput("");
          setPendingFiles([]);
        }
        return filtered;
      });
      setHydratingSessions((prev) => {
        const next = { ...prev };
        delete next[sessionId];
        return next;
      });
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Failed to delete session.";
      setError(message);
    } finally {
      setDeletingSessions((prev) => {
        const next = { ...prev };
        delete next[sessionId];
        return next;
      });
    }
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

    const trimmedMessage = messageInput.trim();
    const optimisticContent =
      trimmedMessage || (pendingFiles.length ? `Uploaded ${pendingFiles.length} file(s)` : "(no prompt)");
    const optimisticMessage: ChatMessage = {
      id: `optimistic-${Date.now()}`,
      role: "user",
      content: optimisticContent,
      createdAt: new Date().toISOString(),
      pending: true,
      uploads: pendingFiles.map(f => ({ 
        id: `temp-${f.name}`, 
        original_filename: f.name,
        session_id: "",
        stored_path: "",
        extraction_status: "pending",
        created_at: new Date().toISOString()
      })),
    };
    const provisionalSessionId = selectedSessionId ?? `temp-${Date.now()}`;
    const nowIso = new Date().toISOString();

    setSessions((prev) => {
      const existing = prev[provisionalSessionId];
      if (existing) {
        return {
          ...prev,
          [provisionalSessionId]: {
            ...existing,
            messages: [...existing.messages, optimisticMessage],
            lastUpdated: nowIso,
          },
        };
      }
      const fallbackTitle = deriveSessionTitle(trimmedMessage, []);
      return {
        ...prev,
        [provisionalSessionId]: {
          id: provisionalSessionId,
          title: fallbackTitle || "New conversation",
          messages: [optimisticMessage],
          uploads: [],
          chronosResponse: null,
          forecastJobId: null,
          lastUpdated: nowIso,
          createdAt: nowIso,
          isHydrated: false,
        },
      };
    });
    setSessionOrder((prev) => [provisionalSessionId, ...prev.filter((id) => id !== provisionalSessionId)]);
    if (!selectedSessionId) {
      setSelectedSessionId(provisionalSessionId);
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await submitChatMessage({
        sessionId: selectedSessionId ?? undefined,
        content: trimmedMessage || undefined,
        files: pendingFiles,
      });
      ingestResponse(response, provisionalSessionId);
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

  const ingestResponse = (response: ChatTurnResponse, originalSessionId?: string) => {
    const sessionId = response.session_id;

    // Filter uploads that belong to the user message we just sent
    // This is a heuristic since the API response separates message and uploads
    // but we want to display them together in the bubble.
    const userUploads = response.uploads.filter(u => u.message_id === response.user_message.id);

    const messageBundle: ChatMessage[] = [
      toChatMessage(response.user_message, userUploads),
      ...response.tool_messages.map(msg => toChatMessage(msg, [])),
      toChatMessage(response.assistant_message, []),
    ];

    setSessions((prev) => {
      const nextSessions = { ...prev };
      const original = originalSessionId ? nextSessions[originalSessionId] : undefined;
      if (originalSessionId && originalSessionId !== sessionId) {
        delete nextSessions[originalSessionId];
      }
      const existing = nextSessions[sessionId] ?? original;
      const fallbackTitle = deriveSessionTitle(response.user_message.content ?? undefined, response.uploads);
      const sessionTitle = response.session_title ?? existing?.title ?? fallbackTitle;
      
      const committedMessages = existing ? existing.messages.filter((msg) => !msg.pending) : [];
      const nextMessages = [...committedMessages, ...messageBundle];
      
      const nowIso = new Date().toISOString();

      nextSessions[sessionId] = {
        id: sessionId,
        title: sessionTitle,
        messages: nextMessages,
        uploads: response.uploads,
        chronosResponse: response.chronos_response ?? existing?.chronosResponse ?? null,
        forecastJobId: response.forecast_job_id ?? existing?.forecastJobId ?? null,
        lastUpdated: nowIso,
        createdAt: existing?.createdAt ?? nowIso,
        isHydrated: true,
      };
      return nextSessions;
    });

    setSessionOrder((prev) => {
      const filtered = prev.filter((id) => id !== sessionId && id !== originalSessionId);
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
        onDeleteSession={(sessionId) => {
          void handleDeleteSession(sessionId);
        }}
        deletingSessions={deletingSessions}
      />
      <main className="relative flex h-full flex-1 flex-col bg-background overflow-hidden">
        <div className="flex-1 min-h-0 flex flex-col">
          {activeSession ? (
            <div className="flex-1 min-h-0 pb-16">
              <MessageList
                messages={activeMessages}
                isLoading={isSubmitting || !!(selectedSessionId && hydratingSessions[selectedSessionId])}
              />
            </div>
          ) : sessionsLoading ? (
            <LoadingState />
          ) : (
            <div className="flex-1 flex flex-col justify-center overflow-y-auto px-12 pb-16">
              <EmptyState />
            </div>
          )}
        </div>

        <div className="pointer-events-none absolute bottom-6 left-0 right-0 z-10 flex justify-center">
          <div className="pointer-events-auto w-full max-w-3xl px-4">
            <ChatComposer
              message={messageInput}
              onMessageChange={setMessageInput}
              files={pendingFiles}
              onFilesChange={handleFilesChange}
              onSubmit={() => {
                void handleSubmit();
              }}
              isSubmitting={isSubmitting}
            />
            {error && (
              <div className="mx-auto mt-2 flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-2 text-xs text-destructive">
                <AlertCircle className="h-3.5 w-3.5" />
                <span>{error}</span>
              </div>
            )}
          </div>
        </div>
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
  <div className="flex flex-col gap-12">
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

const toChatMessage = (dto: MessageDTO, allUploads: UploadArtifactDTO[]): ChatMessage => ({
  id: dto.id,
  role: dto.role,
  content: dto.content ?? "",
  rawPayload: dto.raw_payload ?? undefined,
  createdAt: dto.created_at,
  uploads: allUploads.filter(u => u.message_id === dto.id),
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
