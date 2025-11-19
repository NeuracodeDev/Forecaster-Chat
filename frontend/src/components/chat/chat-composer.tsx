import React, { useRef } from "react";
import { ArrowUp, Paperclip, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface ChatComposerProps {
  message: string;
  onMessageChange: (value: string) => void;
  files: File[];
  onFilesChange: (files: File[]) => void;
  onSubmit: () => void;
  isSubmitting: boolean;
}

export const ChatComposer: React.FC<ChatComposerProps> = ({
  message,
  onMessageChange,
  files,
  onFilesChange,
  onSubmit,
  isSubmitting,
}) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleFileSelection = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files ? Array.from(event.target.files) : [];
    if (selected.length > 0) {
      onFilesChange([...files, ...selected]);
    }
    event.target.value = "";
  };

  const removeFile = (index: number) => {
    const next = files.slice();
    next.splice(index, 1);
    onFilesChange(next);
  };

  const handleSubmit = (event?: React.FormEvent) => {
    event?.preventDefault();
    if (!message.trim() && files.length === 0) {
      return;
    }
    onSubmit();
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  return (
    <form
      className="mx-auto w-full max-w-3xl px-4 py-4"
      onSubmit={handleSubmit}
    >
      {files.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {files.map((file, index) => (
            <span
              key={`${file.name}-${index}`}
              className={cn(
                "inline-flex items-center gap-2 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground shadow-sm",
              )}
            >
              <span className="max-w-[150px] truncate">{file.name}</span>
              <button
                type="button"
                className="text-muted-foreground transition hover:text-destructive"
                onClick={() => removeFile(index)}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="relative flex items-end gap-2 rounded-3xl border border-input bg-background p-2 shadow-sm transition-colors focus-within:border-ring/30 focus-within:ring-1 focus-within:ring-ring/30">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-10 w-10 shrink-0 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip className="h-5 w-5" />
          <span className="sr-only">Attach</span>
        </Button>

        <Textarea
          value={message}
          onChange={(event) => {
             onMessageChange(event.target.value);
             event.target.style.height = 'auto';
             event.target.style.height = `${event.target.scrollHeight}px`;
          }}
          onKeyDown={handleKeyDown}
          placeholder="Message Chronos..."
          className="min-h-[40px] max-h-[200px] flex-1 resize-none border-0 bg-transparent px-2 py-2.5 shadow-none focus-visible:ring-0 text-sm leading-relaxed"
          rows={1}
        />

        <Button
          type="submit"
          size="icon"
          disabled={isSubmitting || (!message.trim() && files.length === 0)}
          className="shrink-0 rounded-full bg-foreground text-background shadow-sm transition-all hover:bg-foreground/90 disabled:opacity-60"
        >
          {isSubmitting ? (
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <ArrowUp className="h-6 w-6" />
          )}
          <span className="sr-only">Send</span>
        </Button>
      </div>

      <p className="mt-3 text-center text-[10px] text-muted-foreground">
        Supports CSV, TSV, JSON, TXT, PDF, and up to 20 images per turn.
      </p>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFileSelection}
        accept="image/*,.csv,.tsv,.json,.jsonl,.txt,.pdf"
      />
    </form>
  );
};
