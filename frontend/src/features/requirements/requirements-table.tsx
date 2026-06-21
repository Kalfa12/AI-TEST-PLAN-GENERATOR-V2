import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Drawer } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useDocuments } from "@/features/documents/hooks";
import { getProjectCoverage, getProjectGaps } from "@/features/traceability/api";
import type { Requirement, RequirementKind } from "@/lib/api/types";
import { useRequirements } from "./hooks";

const ALL_KINDS: RequirementKind[] = [
  "functional",
  "performance",
  "safety",
  "reliability",
  "security",
  "regulatory",
  "environmental",
  "interface",
  "usability",
  "operational",
];

type CoverageFilter = "all" | "covered" | "uncovered";

interface RequirementsTableProps {
  projectId: string;
  selectedRequirementIds?: string[];
  onSelectedRequirementIdsChange?: (ids: string[]) => void;
  onGenerateSelected?: () => void;
}

export function RequirementsTable({
  projectId,
  selectedRequirementIds = [],
  onSelectedRequirementIdsChange,
  onGenerateSelected,
}: RequirementsTableProps) {
  const requirements = useRequirements(projectId);
  const documents = useDocuments(projectId);
  const coverage = useQuery({
    queryKey: ["project-coverage", projectId],
    queryFn: () => getProjectCoverage(projectId),
    enabled: !!projectId,
  });
  const gaps = useQuery({
    queryKey: ["project-gaps", projectId],
    queryFn: () => getProjectGaps(projectId),
    enabled: !!projectId,
  });

  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<RequirementKind | "all">("all");
  const [coverageFilter, setCoverageFilter] = useState<CoverageFilter>("all");
  const [showAll, setShowAll] = useState(false);
  const [activeRequirement, setActiveRequirement] = useState<Requirement | null>(null);

  const selectedSet = useMemo(
    () => new Set(selectedRequirementIds),
    [selectedRequirementIds],
  );

  const documentTitles = useMemo(() => {
    return new Map((documents.data ?? []).map((doc) => [doc.id, doc.title]));
  }, [documents.data]);

  const uncovered = useMemo(
    () => new Set(gaps.data?.uncovered_requirement_ids ?? []),
    [gaps.data],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (requirements.data ?? []).filter((req) => {
      const covered = !uncovered.has(req.id);
      if (kind !== "all" && req.kind !== kind) return false;
      if (coverageFilter === "covered" && !covered) return false;
      if (coverageFilter === "uncovered" && covered) return false;
      if (!needle) return true;
      return [
        req.id,
        req.external_id,
        req.title,
        req.statement,
        req.acceptance_hint,
        req.verbatim_excerpt,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }, [coverageFilter, kind, query, requirements.data, uncovered]);

  const visibleRequirements = showAll ? filtered : filtered.slice(0, 100);
  const visibleIds = visibleRequirements.map((req) => req.id);
  const visibleSelectedCount = visibleIds.filter((id) => selectedSet.has(id)).length;
  const allVisibleSelected =
    visibleIds.length > 0 && visibleSelectedCount === visibleIds.length;

  const total = requirements.data?.length ?? 0;
  const coveredCount = Math.max(total - uncovered.size, 0);
  const isLoading =
    requirements.isLoading || coverage.isLoading || gaps.isLoading || documents.isLoading;

  const updateSelection = (next: string[]) => {
    onSelectedRequirementIdsChange?.(next);
  };

  const toggleRequirement = (id: string) => {
    const next = new Set(selectedSet);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    updateSelection(Array.from(next));
  };

  const toggleVisible = () => {
    const next = new Set(selectedSet);
    if (allVisibleSelected) {
      visibleIds.forEach((id) => next.delete(id));
    } else {
      visibleIds.forEach((id) => next.add(id));
    }
    updateSelection(Array.from(next));
  };

  return (
    <>
      <Card>
        <CardHeader className="space-y-3">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <CardTitle>Requirements</CardTitle>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>{total} extracted</span>
                <span>{coveredCount} covered</span>
                <span>{uncovered.size} uncovered</span>
                <span>{selectedRequirementIds.length} selected</span>
              </div>
            </div>
            <div className="grid gap-2 md:grid-cols-[minmax(220px,1fr)_160px_150px] xl:w-[680px]">
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search requirements"
              />
              <select
                className="h-10 rounded-md border border-border bg-background px-3 text-sm"
                value={kind}
                onChange={(event) =>
                  setKind(event.target.value as RequirementKind | "all")
                }
              >
                <option value="all">All kinds</option>
                {ALL_KINDS.map((item) => (
                  <option key={item} value={item}>
                    {labelize(item)}
                  </option>
                ))}
              </select>
              <select
                className="h-10 rounded-md border border-border bg-background px-3 text-sm"
                value={coverageFilter}
                onChange={(event) =>
                  setCoverageFilter(event.target.value as CoverageFilter)
                }
              >
                <option value="all">All coverage</option>
                <option value="covered">Covered</option>
                <option value="uncovered">Uncovered</option>
              </select>
            </div>
          </div>
          <div className="flex flex-col gap-2 border-t border-border pt-3 md:flex-row md:items-center md:justify-between">
            <div className="text-xs text-muted-foreground">
              Showing {visibleRequirements.length} of {filtered.length} matching
              requirements.
            </div>
            <div className="flex flex-wrap gap-2">
              {filtered.length > 100 && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setShowAll((value) => !value)}
                >
                  {showAll ? "Show first 100" : "Show all"}
                </Button>
              )}
              {selectedRequirementIds.length > 0 && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => updateSelection([])}
                >
                  Clear selection
                </Button>
              )}
              <Button
                type="button"
                size="sm"
                onClick={onGenerateSelected}
                disabled={!onGenerateSelected || selectedRequirementIds.length === 0}
              >
                Generate selected
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardBody className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-9" />
              <Skeleton className="h-9" />
              <Skeleton className="h-9" />
            </div>
          ) : total === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">
              No extracted requirements.
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">
              No requirements match the current filters.
            </div>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH className="w-10">
                    <input
                      type="checkbox"
                      aria-label="Select visible requirements"
                      checked={allVisibleSelected}
                      onChange={toggleVisible}
                    />
                  </TH>
                  <TH className="min-w-[170px]">Requirement</TH>
                  <TH className="min-w-[110px]">Kind</TH>
                  <TH className="min-w-[90px]">Priority</TH>
                  <TH className="min-w-[130px]">Coverage</TH>
                  <TH className="min-w-[240px]">Statement</TH>
                  <TH className="min-w-[180px]">Source</TH>
                  <TH className="w-24"></TH>
                </TR>
              </THead>
              <TBody>
                {visibleRequirements.map((req) => (
                  <RequirementRow
                    key={req.id}
                    requirement={req}
                    coveredBy={coverage.data?.[req.id] ?? []}
                    sourceTitle={documentTitles.get(req.source_document_id)}
                    uncovered={uncovered.has(req.id)}
                    selected={selectedSet.has(req.id)}
                    onToggleSelected={() => toggleRequirement(req.id)}
                    onInspect={() => setActiveRequirement(req)}
                  />
                ))}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>

      <RequirementDrawer
        requirement={activeRequirement}
        coveredBy={activeRequirement ? coverage.data?.[activeRequirement.id] ?? [] : []}
        sourceTitle={
          activeRequirement
            ? documentTitles.get(activeRequirement.source_document_id)
            : undefined
        }
        open={activeRequirement !== null}
        onOpenChange={(open) => {
          if (!open) setActiveRequirement(null);
        }}
      />
    </>
  );
}

function RequirementRow({
  requirement,
  coveredBy,
  sourceTitle,
  uncovered,
  selected,
  onToggleSelected,
  onInspect,
}: {
  requirement: Requirement;
  coveredBy: string[];
  sourceTitle?: string;
  uncovered: boolean;
  selected: boolean;
  onToggleSelected: () => void;
  onInspect: () => void;
}) {
  return (
    <TR>
      <TD>
        <input
          type="checkbox"
          aria-label={`Select ${requirement.external_id ?? requirement.id}`}
          checked={selected}
          onChange={onToggleSelected}
        />
      </TD>
      <TD className="font-mono text-xs">
        <div className="font-medium text-foreground">
          {requirement.external_id ?? requirement.id}
        </div>
        {requirement.external_id && (
          <div className="mt-1 text-muted-foreground">{requirement.id}</div>
        )}
      </TD>
      <TD>
        <Badge tone="info">{labelize(requirement.kind)}</Badge>
      </TD>
      <TD>
        <Badge
          tone={
            requirement.priority <= 2
              ? "danger"
              : requirement.priority === 3
                ? "warning"
                : "default"
          }
        >
          P{requirement.priority}
        </Badge>
      </TD>
      <TD>
        {uncovered ? (
          <Badge tone="danger">Uncovered</Badge>
        ) : (
          <Badge tone="success">
            {coveredBy.length} test{coveredBy.length === 1 ? "" : "s"}
          </Badge>
        )}
      </TD>
      <TD>
        <div className="max-w-[680px]">
          <div className="font-medium leading-5">{requirement.title}</div>
          <div className="mt-1 line-clamp-3 text-sm leading-5 text-muted-foreground">
            {requirement.statement}
          </div>
          {requirement.acceptance_hint && (
            <div className="mt-2 text-xs text-muted-foreground">
              Acceptance: {requirement.acceptance_hint}
            </div>
          )}
        </div>
      </TD>
      <TD className="text-sm text-muted-foreground">
        <div className="max-w-[280px] truncate text-foreground">
          {sourceTitle ?? requirement.source_document_id}
        </div>
        <div className="mt-1">
          {requirement.source_chunk_ids.length} chunk
          {requirement.source_chunk_ids.length === 1 ? "" : "s"}
        </div>
      </TD>
      <TD>
        <Button type="button" size="sm" variant="outline" onClick={onInspect}>
          Inspect
        </Button>
      </TD>
    </TR>
  );
}

function RequirementDrawer({
  requirement,
  coveredBy,
  sourceTitle,
  open,
  onOpenChange,
}: {
  requirement: Requirement | null;
  coveredBy: string[];
  sourceTitle?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!requirement) {
    return null;
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <div className="flex h-full flex-col">
        <div className="border-b border-border p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-mono text-xs text-muted-foreground">
                {requirement.external_id ?? requirement.id}
              </div>
              <h2 className="mt-1 text-lg font-semibold">{requirement.title}</h2>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Close
            </Button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge tone="info">{labelize(requirement.kind)}</Badge>
            <Badge tone={requirement.priority <= 2 ? "danger" : "warning"}>
              P{requirement.priority}
            </Badge>
            <Badge tone={coveredBy.length > 0 ? "success" : "danger"}>
              {coveredBy.length > 0 ? `${coveredBy.length} tests` : "Uncovered"}
            </Badge>
          </div>
        </div>
        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          <DetailBlock title="Statement">{requirement.statement}</DetailBlock>
          {requirement.acceptance_hint && (
            <DetailBlock title="Acceptance hint">
              {requirement.acceptance_hint}
            </DetailBlock>
          )}
          {requirement.rationale && (
            <DetailBlock title="Rationale">{requirement.rationale}</DetailBlock>
          )}
          {requirement.verbatim_excerpt && (
            <DetailBlock title="Verbatim excerpt">
              {requirement.verbatim_excerpt}
            </DetailBlock>
          )}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
              Source
            </h3>
            <div className="mt-2 rounded-md border border-border p-3 text-sm">
              <div className="font-medium">
                {sourceTitle ?? requirement.source_document_id}
              </div>
              {requirement.source_section_id && (
                <div className="mt-1 text-muted-foreground">
                  Section {requirement.source_section_id}
                </div>
              )}
              <div className="mt-2 flex flex-wrap gap-1">
                {requirement.source_chunk_ids.map((chunkId) => (
                  <Badge key={chunkId} tone="default" className="font-mono">
                    {chunkId}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
          {coveredBy.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
                Covered by
              </h3>
              <div className="mt-2 flex flex-wrap gap-1">
                {coveredBy.map((testId) => (
                  <Badge key={testId} tone="success" className="font-mono">
                    {testId}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </Drawer>
  );
}

function DetailBlock({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
        {title}
      </h3>
      <p className="mt-2 text-sm leading-6">{children}</p>
    </div>
  );
}

function labelize(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
