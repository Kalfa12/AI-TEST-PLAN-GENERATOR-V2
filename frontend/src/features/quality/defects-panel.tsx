import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  DefectInstance,
  DefectReport,
  DefectSeverity,
} from "@/lib/api/types";

const SEVERITY_ORDER: DefectSeverity[] = ["critical", "major", "minor"];

const TONE_BY_SEVERITY: Record<DefectSeverity, "danger" | "warning" | "info"> = {
  critical: "danger",
  major: "warning",
  minor: "info",
};

// Above this defect count the panel collapses by default — keeps the
// test-case table visible instead of pushing it below the fold.
const AUTO_COLLAPSE_THRESHOLD = 10;

function formatDefectType(id: string): string {
  return id
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

interface DefectsPanelProps {
  report: DefectReport;
}

export function DefectsPanel({ report }: DefectsPanelProps) {
  const total = report.defects.length;
  const counts = report.summary;
  const [open, setOpen] = useState(total <= AUTO_COLLAPSE_THRESHOLD);

  if (total === 0) {
    return (
      <Card>
        <CardHeader className="flex items-center justify-between">
          <CardTitle>Quality review</CardTitle>
          <Badge tone="success">No defects detected</Badge>
        </CardHeader>
        <CardBody className="text-sm text-muted-foreground">
          Static checks and the LLM reviewer agreed: this plan meets the
          taxonomy thresholds for the defects we screen.
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-2">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-2 text-left"
        >
          <svg
            className={`w-4 h-4 transition-transform ${open ? "rotate-90" : ""}`}
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
          >
            <path d="M6 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <CardTitle>Quality review</CardTitle>
          <span className="text-xs text-muted-foreground ml-1">
            ({total} total)
          </span>
        </button>
        <div className="flex items-center gap-2">
          {SEVERITY_ORDER.map((sev) => {
            const n = counts[sev] ?? 0;
            if (n === 0) return null;
            return (
              <Badge key={sev} tone={TONE_BY_SEVERITY[sev]}>
                {n} {sev}
              </Badge>
            );
          })}
        </div>
      </CardHeader>
      {open && (
        <CardBody className="space-y-4 p-0">
          {SEVERITY_ORDER.map((sev) => {
            const items = report.defects.filter((d) => d.severity === sev);
            if (!items.length) return null;
            return <SeverityGroup key={sev} severity={sev} items={items} />;
          })}
        </CardBody>
      )}
    </Card>
  );
}

function SeverityGroup({
  severity,
  items,
}: {
  severity: DefectSeverity;
  items: DefectInstance[];
}) {
  return (
    <div className="border-t border-border first:border-t-0">
      <div className="bg-muted/40 px-4 py-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {severity} ({items.length})
      </div>
      <ul className="divide-y divide-border">
        {items.map((d) => (
          <li key={d.id} className="px-4 py-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={TONE_BY_SEVERITY[severity]}>
                {formatDefectType(d.defect_type)}
              </Badge>
              <span className="text-xs text-muted-foreground font-mono">
                {d.target_kind.replace("_", " ")} · {d.target_id}
              </span>
            </div>
            <p className="mt-2 text-foreground">{d.evidence}</p>
            {d.suggestion && (
              <p className="mt-1 text-muted-foreground">
                <span className="font-medium">Fix:</span> {d.suggestion}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
