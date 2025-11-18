import React from "react";
import DOMPurify from "dompurify";
import { FileJson2, Loader2 } from "lucide-react";

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
      <div className="flex min-h-full flex-col gap-6 p-6">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isLoading && (
          <div className="flex justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
    </ScrollArea>
  );
};

const MessageBubble: React.FC<{ message: ChatMessage }> = ({ message }) => {
  const { role, content, rawPayload } = message;

  if (role === "tool") {
    return (
      <div className="flex flex-col gap-3 rounded-lg border border-dashed border-muted-foreground/40 bg-muted/30 p-4 text-sm text-muted-foreground">
        {content ? (
          <div className="whitespace-pre-wrap">{content}</div>
        ) : (
          <div className="italic text-muted-foreground">Tool output received.</div>
        )}
        {rawPayload?.chronos_response ? (
          <details className="rounded-md border border-border bg-background">
            <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium">
              <FileJson2 className="h-4 w-4" />
              Chronos response JSON
            </summary>
            <pre className="max-h-96 overflow-auto px-3 pb-4 text-xs leading-relaxed">
              {JSON.stringify(rawPayload.chronos_response, null, 2)}
            </pre>
          </details>
        ) : null}
      </div>
    );
  }

  const alignment =
    role === "assistant"
      ? "items-start"
      : role === "user"
        ? "items-end justify-end"
        : "items-start";

  const bubbleClasses =
    role === "assistant"
      ? "bg-card text-card-foreground shadow"
      : role === "user"
        ? "bg-primary text-primary-foreground"
        : "bg-muted text-muted-foreground";

  const sanitizedHtml =
    role === "assistant" && content ? DOMPurify.sanitize(content, { USE_PROFILES: { html: true } }) : null;

  return (
    <div className={cn("flex flex-col gap-2", alignment)}>
      <div className={cn("max-w-3xl rounded-lg px-4 py-3 text-sm leading-relaxed", bubbleClasses)}>
        {role === "assistant" && sanitizedHtml ? (
          <div className="chat-html" dangerouslySetInnerHTML={{ __html: sanitizedHtml }} />
        ) : (
          <span className="whitespace-pre-wrap">{content}</span>
        )}
      </div>
      <span className="text-xs uppercase tracking-wide text-muted-foreground">
        {new Date(message.createdAt).toLocaleTimeString()}
      </span>
    </div>
  );
};

