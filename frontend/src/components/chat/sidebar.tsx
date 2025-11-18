import { Plus, SquarePen } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";

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
    <aside className="flex h-full w-72 flex-col border-r bg-muted/30">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Forecaster</p>
          <h1 className="text-lg font-bold">Chronos Chat</h1>
        </div>
        <Button size="icon" variant="secondary" onClick={onCreateSession}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <nav className="flex flex-col gap-1 p-2">
          {sessions.length === 0 ? (
            <div className="rounded-md border border-dashed border-muted-foreground/40 p-4 text-xs text-muted-foreground">
              Start a conversation to see it appear here.
            </div>
          ) : (
            sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                className={cn(
                  "flex flex-col gap-1 rounded-md px-3 py-2 text-left transition-colors hover:bg-accent",
                  selectedSessionId === session.id ? "bg-accent text-accent-foreground" : "text-muted-foreground",
                )}
                onClick={() => onSelectSession(session.id)}
              >
                <span className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <SquarePen className="h-4 w-4 text-muted-foreground" />
                  {session.title}
                </span>
                <span className="text-xs uppercase tracking-wide text-muted-foreground">
                  {new Date(session.lastUpdated).toLocaleString()}
                </span>
              </button>
            ))
          )}
        </nav>
      </ScrollArea>
      <div className="border-t px-4 py-3 text-xs text-muted-foreground">
        Need help? Join the community on GitHub.
      </div>
    </aside>
  );
};

