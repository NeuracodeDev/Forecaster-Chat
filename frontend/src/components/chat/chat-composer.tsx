import React, { useRef } from "react";
import { Paperclip, Send, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!message.trim() && files.length === 0) {
      return;
    }
    onSubmit();
  };

  return (
    <form className="flex flex-col gap-4 border-t bg-background/95 p-4 shadow-[0_-4px_12px_rgba(0,0,0,0.04)]" onSubmit={handleSubmit}>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="secondary"
          className="h-10 w-10 shrink-0"
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip className="h-4 w-4" />
        </Button>
        <Input
          value={message}
          onChange={(event) => onMessageChange(event.target.value)}
          placeholder="Ask Chronos a question..."
          className="flex-1"
          autoFocus
        />
        <Button type="submit" disabled={isSubmitting} className="h-10 w-10 shrink-0">
          {isSubmitting ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>

      {files.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {files.map((file, index) => (
            <span
              key={`${file.name}-${index}`}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border border-border bg-muted/60 px-3 py-1 text-xs",
                "text-muted-foreground",
              )}
            >
              <span className="max-w-[160px] truncate font-medium text-foreground">{file.name}</span>
              <button
                type="button"
                className="text-muted-foreground transition-colors hover:text-destructive"
                onClick={() => removeFile(index)}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}

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

