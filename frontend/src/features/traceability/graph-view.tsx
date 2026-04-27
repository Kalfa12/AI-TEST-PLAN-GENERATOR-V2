import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import type { Core, ElementDefinition } from "cytoscape";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { getLineage } from "./api";
import type { LineageResponse, TraceNode } from "@/lib/api/types";

const RISK_COLOR: Record<string, string> = {
  "1": "#10b981",
  "2": "#f59e0b",
  "3": "#ef4444",
};

function nodeColor(node: TraceNode): string {
  const risk = node.attributes?.risk_level;
  if (risk !== undefined && risk !== null) {
    return RISK_COLOR[String(risk)] ?? "#64748b";
  }
  return "#64748b";
}

function buildElements(lineage: LineageResponse): ElementDefinition[] {
  const elements: ElementDefinition[] = [];
  const allNodes: Record<string, TraceNode> = {
    [lineage.root.id]: lineage.root,
    ...lineage.nodes,
  };
  for (const id of Object.keys(allNodes)) {
    const n = allNodes[id];
    elements.push({
      data: {
        id,
        label: id,
        kind: n.type ?? "",
        color: nodeColor(n),
      },
    });
  }
  for (const e of lineage.edges) {
    elements.push({
      data: {
        id: `${e.source}->${e.target}:${e.kind}`,
        source: e.source,
        target: e.target,
        kind: e.kind,
      },
    });
  }
  return elements;
}

export function TraceabilityGraphPage() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const toast = useToast();
  const [artefactId, setArtefactId] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [depth, setDepth] = useState(3);
  const [lineage, setLineage] = useState<LineageResponse | null>(null);
  const [selected, setSelected] = useState<TraceNode | null>(null);
  const [loading, setLoading] = useState(false);

  const loadLineage = async (id: string, d: number) => {
    setLoading(true);
    try {
      const data = await getLineage(id, d);
      setLineage(data);
      setActiveId(id);
    } catch (e) {
      toast.push({
        title: "Failed to load lineage",
        description: (e as Error).message,
        tone: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!containerRef.current || !lineage) return;
    cyRef.current?.destroy();
    const cy = cytoscape({
      container: containerRef.current,
      elements: buildElements(lineage),
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: "#1f2937",
            "text-valign": "bottom",
            "text-margin-y": 4,
            "font-size": 10,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(kind)",
            "font-size": 8,
            "text-background-color": "#fff",
            "text-background-opacity": 0.8,
          },
        },
      ],
      layout: { name: "breadthfirst", directed: true, padding: 16 },
    });
    cy.on("tap", "node", (evt) => {
      const id = evt.target.id() as string;
      const node = lineage.root.id === id ? lineage.root : lineage.nodes[id];
      if (node) setSelected(node);
    });
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [lineage]);

  const onExportPng = () => {
    if (!cyRef.current) return;
    const png = cyRef.current.png({ output: "blob", scale: 2 });
    const url = URL.createObjectURL(png);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${activeId ?? "trace"}.png`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Traceability</h1>
          <p className="text-sm text-muted-foreground">
            Explore upstream ancestors of any artefact in the cross-document graph.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onExportPng} disabled={!lineage}>
          Export PNG
        </Button>
      </div>

      <Card>
        <CardBody className="flex items-end gap-2">
          <div className="flex-1 space-y-1">
            <label className="text-xs font-medium">Artefact ID</label>
            <Input
              value={artefactId}
              placeholder="req_abc123 or tc_xyz"
              onChange={(e) => setArtefactId(e.target.value)}
            />
          </div>
          <div className="space-y-1 w-24">
            <label className="text-xs font-medium">Depth</label>
            <Input
              type="number"
              min={1}
              max={10}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value) || 3)}
            />
          </div>
          <Button
            disabled={!artefactId.trim() || loading}
            onClick={() => loadLineage(artefactId.trim(), depth)}
          >
            {loading ? "Loading…" : "Load"}
          </Button>
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <Card className="lg:col-span-3">
          <CardBody className="p-0">
            {loading ? (
              <Skeleton className="h-[500px]" />
            ) : (
              <div
                ref={containerRef}
                className="w-full h-[500px] bg-muted/20 rounded-md"
              />
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Selection</CardTitle>
          </CardHeader>
          <CardBody className="text-sm">
            {selected ? (
              <div className="space-y-2">
                <div>
                  <div className="text-xs uppercase text-muted-foreground">ID</div>
                  <div className="font-mono">{selected.id}</div>
                </div>
                {selected.type && (
                  <div>
                    <div className="text-xs uppercase text-muted-foreground">Type</div>
                    <div>{selected.type}</div>
                  </div>
                )}
                {Object.keys(selected.attributes ?? {}).length > 0 && (
                  <div>
                    <div className="text-xs uppercase text-muted-foreground">
                      Attributes
                    </div>
                    <pre className="bg-muted/40 p-2 rounded text-xs overflow-auto">
                      {JSON.stringify(selected.attributes, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-muted-foreground">Click a node to inspect it.</p>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
