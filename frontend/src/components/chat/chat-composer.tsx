import React, { useRef } from "react";
import { ArrowUp, Paperclip, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

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
      className="mx-auto w-full max-w-3xl"
      onSubmit={handleSubmit}
    >
      {files.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2 px-2">
          {files.map((file, index) => (
            <span
              key={`${file.name}-${index}`}
              className="inline-flex items-center gap-2 rounded-lg border border-border bg-background/50 backdrop-blur-sm px-2 py-1 text-[10px] font-medium text-foreground shadow-sm"
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

      <div className="relative flex items-end gap-1.5 rounded-[26px] border border-black/20 bg-background/45 backdrop-blur-2xl p-1.5 shadow-sm transition-all focus-within:bg-background/65 hover:bg-background/55">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0 rounded-full text-muted-foreground hover:bg-muted/30 hover:text-foreground transition-colors"
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip className="h-4 w-4" />
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
          className="min-h-[20px] max-h-[200px] flex-1 resize-none border-0 bg-transparent px-2 py-2 shadow-none focus-visible:ring-0 text-sm leading-normal placeholder:text-muted-foreground/50"
          rows={1}
        />

        <Button
          type="submit"
          size="icon"
          disabled={isSubmitting || (!message.trim() && files.length === 0)}
          className="shrink-0 h-8 w-8 rounded-full bg-foreground text-background shadow-sm transition-all hover:bg-foreground/90 disabled:opacity-50"
        >
          {isSubmitting ? (
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <ArrowUp className="h-4 w-4" />
          )}
          <span className="sr-only">Send</span>
        </Button>
      </div>

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
