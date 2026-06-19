import { useEffect, useRef, useState } from "react";
import { http } from "@/lib/api/http";
import { readTokens } from "@/lib/auth/storage";

const PIPELINE: { key: string; label: string; description: string }[] = [
  { key: "analyst",      label: "Document Analyst",     description: "Summarising corpus & detecting gaps" },
  { key: "extractor",    label: "Req. Extractor",       description: "Extracting testable requirements" },
  { key: "architect",    label: "Test Architect",        description: "Designing strategy & scope" },
  { key: "generator",    label: "Test Generator",        description: "Writing test cases per requirement" },
  { key: "traceability", label: "Traceability Agent",   description: "Validating requirement coverage" },
  { key: "reviewer",     label: "Reviewer",             description: "Critiquing plan quality" },
  { key: "planner",      label: "Planner",              description: "Scheduling test campaign" },
];

type StepState = "pending" | "running" | "done" | "error";

interface StepStatus {
  state: StepState;
  startedAt?: number;
  durationMs?: number;
}

interface AgentEvent {
  kind: "agent_start" | "agent_done" | "agent_error";
  actor: string;
  content: string;
}

interface Props {
  sessionId: string | null;
  jobStatus: string | null;
  jobError: string | null;
}

export function AgentProgress({ sessionId, jobStatus, jobError }: Props) {
  const [steps, setSteps] = useState<Record<string, StepStatus>>(() =>
    Object.fromEntries(PIPELINE.map((s) => [s.key, { state: "pending" as StepState }]))
  );
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number>(Date.now());
  const esRef = useRef<EventSource | null>(null);

  // Elapsed timer
  useEffect(() => {
    if (jobStatus === "succeeded" || jobStatus === "failed") return;
    const id = setInterval(() => setElapsed(Date.now() - startRef.current), 1000);
    return () => clearInterval(id);
  }, [jobStatus]);

  // SSE connection for per-agent events
  useEffect(() => {
    if (!sessionId) return;

    const token = readTokens()?.access;
    const baseUrl = (http.defaults.baseURL ?? "http://localhost:8000").replace(/\/$/, "");
    const url = `${baseUrl}/sessions/${sessionId}/events${token ? `?token=${token}` : ""}`;

    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("agent_progress", (ev) => {
      try {
        const data: AgentEvent = JSON.parse(ev.data);
        const key = data.actor;
        if (!PIPELINE.find((p) => p.key === key)) return;

        setSteps((prev) => {
          const now = Date.now();
          if (data.kind === "agent_start") {
            return { ...prev, [key]: { state: "running", startedAt: now } };
          }
          if (data.kind === "agent_done") {
            const started = prev[key]?.startedAt ?? now;
            return { ...prev, [key]: { state: "done", startedAt: started, durationMs: now - started } };
          }
          if (data.kind === "agent_error") {
            return { ...prev, [key]: { ...prev[key], state: "error" } };
          }
          return prev;
        });
      } catch {
        // ignore parse errors
      }
    });

    es.onerror = () => es.close();

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [sessionId]);

  // Close SSE when job finishes
  useEffect(() => {
    if (jobStatus === "succeeded" || jobStatus === "failed") {
      esRef.current?.close();
      // Mark remaining running steps as done on success
      if (jobStatus === "succeeded") {
        setSteps((prev) => {
          const next = { ...prev };
          for (const k of Object.keys(next)) {
            if (next[k].state === "running") next[k] = { ...next[k], state: "done" };
          }
          return next;
        });
      }
    }
  }, [jobStatus]);

  const isFinished = jobStatus === "succeeded" || jobStatus === "failed";
  const elapsedStr = formatElapsed(elapsed);

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {!isFinished && (
            <span className="inline-block w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          )}
          {jobStatus === "succeeded" && (
            <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
          )}
          {jobStatus === "failed" && (
            <span className="inline-block w-2 h-2 rounded-full bg-red-500" />
          )}
          <span className="text-sm font-medium">
            {jobStatus === "succeeded"
              ? "Plan generation complete"
              : jobStatus === "failed"
              ? "Generation failed"
              : "Generating plan…"}
          </span>
        </div>
        <span className="text-xs text-muted-foreground font-mono">{elapsedStr}</span>
      </div>

      {/* Error banner */}
      {jobError && (
        <div className="rounded bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
          {jobError}
        </div>
      )}

      {/* Pipeline steps */}
      <div className="space-y-1">
        {PIPELINE.map((step, idx) => {
          const s = steps[step.key] ?? { state: "pending" };
          return (
            <div key={step.key} className="flex items-center gap-3">
              {/* Connector line */}
              <div className="flex flex-col items-center">
                <StepIcon state={s.state} />
                {idx < PIPELINE.length - 1 && (
                  <div className={`w-px flex-1 mt-0.5 ${s.state === "done" ? "bg-green-400" : "bg-border"}`} style={{ height: 12 }} />
                )}
              </div>
              {/* Content */}
              <div className="flex-1 min-w-0 pb-1">
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-medium ${s.state === "pending" ? "text-muted-foreground" : ""}`}>
                    {step.label}
                  </span>
                  {s.state === "running" && (
                    <span className="text-xs text-blue-500 animate-pulse">running…</span>
                  )}
                  {s.state === "done" && s.durationMs && (
                    <span className="text-xs text-muted-foreground">{Math.round(s.durationMs / 1000)}s</span>
                  )}
                  {s.state === "error" && (
                    <span className="text-xs text-red-500">error</span>
                  )}
                </div>
                {s.state !== "pending" && (
                  <p className="text-xs text-muted-foreground">{step.description}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Session ID for debugging */}
      {sessionId && (
        <p className="text-xs text-muted-foreground font-mono truncate">
          session: {sessionId}
        </p>
      )}
    </div>
  );
}

function StepIcon({ state }: { state: StepState }) {
  if (state === "done") {
    return (
      <svg className="w-4 h-4 text-green-500 shrink-0" viewBox="0 0 16 16" fill="currentColor">
        <circle cx="8" cy="8" r="8" className="opacity-20" />
        <path d="M5 8l2 2 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (state === "running") {
    return (
      <svg className="w-4 h-4 text-blue-500 shrink-0 animate-spin" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" strokeDasharray="20 18" strokeLinecap="round" />
      </svg>
    );
  }
  if (state === "error") {
    return (
      <svg className="w-4 h-4 text-red-500 shrink-0" viewBox="0 0 16 16" fill="currentColor">
        <circle cx="8" cy="8" r="8" className="opacity-20" />
        <path d="M5 5l6 6M11 5l-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  // pending
  return (
    <div className="w-4 h-4 rounded-full border-2 border-border shrink-0" />
  );
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  if (m > 0) return `${m}m ${s % 60}s`;
  return `${s}s`;
}
