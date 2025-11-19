import React from "react";
import DOMPurify from "dompurify";
import { Bot, FileJson2, Loader2, User, Wrench } from "lucide-react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { MessageRole } from "@/types/chat";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content?: string | null;
  rawPayload?: Record<string, unknown> | null;
  createdAt: string;
}

export interface MessageListProps {
  messages: ChatMessage[];
  isLoading?: boolean;
}

export const MessageList: React.FC<MessageListProps> = ({ messages, isLoading }) => {
  return (
    <ScrollArea className="h-full">
      <div className="flex min-h-full w-full flex-col gap-8 px-8 py-10">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isLoading && (
          <div className="flex items-center justify-center gap-3 rounded-2xl border border-dashed border-border/70 bg-muted/40 px-5 py-4 text-sm font-medium text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Chronos is processing your request…
          </div>
        )}
      </div>
    </ScrollArea>
  );
};

const MessageBubble: React.FC<{ message: ChatMessage }> = ({ message }) => {
  const { role, content, rawPayload, createdAt } = message;

  if (role === "tool") {
    return (
      <div className="fade-in rounded-xl border border-dashed border-border/70 bg-muted/60 p-4 text-sm text-muted-foreground shadow-sm">
        <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Wrench className="h-4 w-4" />
          Forecast engine
        </div>
        {content ? (
          <div className="whitespace-pre-wrap">{content}</div>
        ) : (
          <div className="italic text-muted-foreground">Tool output received.</div>
        )}
        {rawPayload?.chronos_response ? (
          <details className="mt-3 rounded-xl border border-border bg-card text-left text-foreground">
            <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm font-semibold">
              <FileJson2 className="h-4 w-4" />
              View Chronos response JSON
            </summary>
            <pre className="max-h-96 overflow-auto border-t border-border px-4 py-3 text-xs leading-relaxed">
              {JSON.stringify(rawPayload.chronos_response, null, 2)}
            </pre>
          </details>
        ) : null}
      </div>
    );
  }

  const isUser = role === "user";
  const isAssistant = role === "assistant";

  const sanitizedHtml =
    isAssistant && content ? DOMPurify.sanitize(content, { USE_PROFILES: { html: true } }) : null;

  return (
    <div className={cn("fade-in flex items-start gap-4", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-xs font-semibold shadow-sm",
          isUser ? "bg-foreground text-background" : "bg-muted text-foreground",
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div className={cn("flex flex-col gap-2", isUser ? "items-end" : "items-start")}>
        <div
          className={cn(
            "max-w-3xl rounded-xl border px-5 py-4 text-sm leading-relaxed shadow-sm",
            isUser ? "bg-foreground text-background border-transparent" : "bg-card text-card-foreground",
          )}
        >
          {isAssistant && sanitizedHtml ? (
            <div className="chat-html" dangerouslySetInnerHTML={{ __html: sanitizedHtml }} />
          ) : (
            <span className="whitespace-pre-wrap">{content}</span>
          )}
        </div>
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {new Date(createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    </div>
  );
};
