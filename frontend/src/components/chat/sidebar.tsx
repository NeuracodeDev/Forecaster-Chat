import { ListFilter, Plus, SquarePen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

export interface ChatSessionSummary {
  id: string;
  title: string;
  lastUpdated: string;
}

interface SidebarProps {
  sessions: ChatSessionSummary[];
  selectedSessionId: string | null;
  onSelectSession: (sessionId: string | null) => void;
  onCreateSession: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  selectedSessionId,
  onSelectSession,
  onCreateSession,
}) => {
  return (
    <aside className="flex h-full w-64 flex-col border-r border-sidebar-border bg-sidebar px-4 py-4 text-sidebar-foreground">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.35em] text-muted-foreground">Forecaster</p>
          <h1 className="mt-1 text-lg font-semibold tracking-tight">Chronos Chat</h1>
        </div>
        <Button
          size="icon"
          className="h-9 w-9 rounded-lg border border-border bg-sidebar-primary/90 text-sidebar-primary-foreground shadow-sm transition hover:bg-sidebar-primary"
          onClick={onCreateSession}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      <div className="mt-6 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <span>Sessions</span>
      </div>

      <ScrollArea className="mt-3 flex-1">
        <nav className="space-y-2 pr-3">
          {sessions.length === 0 ? (
            <div className="rounded-lg border border-dashed border-sidebar-border/70 px-3 py-4 text-sm text-muted-foreground">
              Start a conversation to see it here.
            </div>
          ) : (
            sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => onSelectSession(session.id)}
                className={cn(
                  "flex w-full flex-col rounded-lg border px-3 py-2 text-left transition-colors",
                  selectedSessionId === session.id
                    ? "border-sidebar-ring bg-sidebar-accent"
                    : "border-transparent hover:bg-sidebar-accent/70",
                )}
              >
                <span className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <SquarePen className="h-4 w-4 text-muted-foreground" />
                  <span className="truncate">{session.title}</span>
                </span>
                <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  {formatRelativeTime(session.lastUpdated)}
                </span>
              </button>
            ))
          )}
        </nav>
      </ScrollArea>
    </aside>
  );
};

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diffMs < minute) return "Just now";
  if (diffMs < hour) return `${Math.floor(diffMs / minute)}m ago`;
  if (diffMs < day) return `${Math.floor(diffMs / hour)}h ago`;
  if (diffMs < day * 7) return `${Math.floor(diffMs / day)}d ago`;
  return date.toLocaleDateString();
}

