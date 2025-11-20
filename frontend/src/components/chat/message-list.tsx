import React, { useEffect, useRef } from "react";
import DOMPurify from "dompurify";
import { ChevronRight, File, Loader2, Wrench } from "lucide-react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { MessageRole, UploadArtifactDTO } from "@/types/chat";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content?: string | null;
  rawPayload?: Record<string, unknown> | null;
  createdAt: string;
  pending?: boolean;
  uploads?: UploadArtifactDTO[];
}

export interface MessageListProps {
  messages: ChatMessage[];
  isLoading?: boolean;
}

export const MessageList: React.FC<MessageListProps> = ({ messages, isLoading }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const lastMessageCount = useRef(messages.length);
  const wasAtBottom = useRef(true);

  const checkScrollPosition = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    wasAtBottom.current = scrollHeight - scrollTop - clientHeight <= 50;
  };

  useEffect(() => {
    if (!scrollRef.current || !endRef.current) return;
    const isNewMessage = messages.length > lastMessageCount.current;
    const shouldScroll = isNewMessage || wasAtBottom.current;
    if (shouldScroll) {
      endRef.current.scrollIntoView({ behavior: "smooth" });
    }
    lastMessageCount.current = messages.length;
  }, [messages, isLoading]);

  return (
    <ScrollArea
      className="h-full w-full"
      ref={scrollRef}
      onScroll={checkScrollPosition}
    >
      <div className="flex min-h-full w-full flex-col gap-6 px-4 py-6 md:px-10 md:py-8">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isLoading && (
          <div className="flex items-center justify-center gap-3 rounded-xl border border-dashed border-border/70 bg-muted/30 px-4 py-3 text-sm font-medium text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Chronos is forecasting…
          </div>
        )}
        <div ref={endRef} />
      </div>
    </ScrollArea>
  );
};

const MessageBubble: React.FC<{ message: ChatMessage }> = ({ message }) => {
  const { role, content, rawPayload, createdAt, pending, uploads } = message;

  if (role === "tool") {
    // Ultra-compact status line for tool outputs
    const isJson = !!rawPayload?.chronos_response;
    const label = isJson ? "Chronos Raw Output" : "Forecast Engine Log";
    
    return (
      <details className="group fade-in w-full text-xs text-muted-foreground/80 transition-colors">
        <summary className="flex cursor-pointer items-center gap-2 py-1 font-medium hover:text-foreground select-none justify-start">
          <Wrench className="h-3 w-3 opacity-60" />
          <span className="uppercase tracking-wider text-[10px]">{label}</span>
          <ChevronRight className="h-3 w-3 opacity-50 transition-transform group-open:rotate-90" />
        </summary>
        <div className="mt-2 rounded-lg border border-border/50 bg-muted/30 px-4 py-3">
           {isJson ? (
             <pre className="max-h-64 overflow-auto text-[10px] leading-relaxed font-mono whitespace-pre-wrap text-foreground/90">
               {JSON.stringify(rawPayload?.chronos_response, null, 2)}
             </pre>
           ) : (
             <div className="whitespace-pre-wrap font-mono text-[10px] text-foreground/90">{content}</div>
           )}
        </div>
      </details>
    );
  }

  const isUser = role === "user";
  const isAssistant = role === "assistant";
  const sanitizedHtml = isAssistant && content ? DOMPurify.sanitize(content, { USE_PROFILES: { html: true } }) : null;

  return (
    <div className={cn("fade-in flex w-full flex-col gap-1", isUser ? "items-end" : "items-start")}>
      <div className={cn("flex flex-col gap-2 max-w-3xl", isUser ? "items-end" : "items-start")}>
        {isUser && uploads && uploads.length > 0 && (
          <div className="flex flex-wrap justify-end gap-2">
            {uploads.map((file) => (
              <div key={file.id} className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1 text-[10px] text-muted-foreground shadow-sm">
                <File className="h-3 w-3" />
                <span className="max-w-[120px] truncate">{file.original_filename}</span>
              </div>
            ))}
          </div>
        )}
        <div
          className={cn(
            "rounded-2xl px-5 py-3 text-sm leading-relaxed shadow-sm",
            isUser 
              ? "bg-foreground text-background rounded-br-sm" 
              : "bg-card text-card-foreground border border-border/50 rounded-bl-sm",
            pending ? "opacity-80" : "",
          )}
        >
        {isAssistant && sanitizedHtml ? (
          <div className="chat-html" dangerouslySetInnerHTML={{ __html: sanitizedHtml }} />
        ) : (
          <span className="whitespace-pre-wrap break-words">{content ?? <span className="italic opacity-50">No content</span>}</span>
        )}
        </div>
      </div>
      <span className="px-1 text-[10px] uppercase tracking-wider text-muted-foreground/50">
        {pending ? "Sending…" : new Date(createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
      </span>
    </div>
  );
};
