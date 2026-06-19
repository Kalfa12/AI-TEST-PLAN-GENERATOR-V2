import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import {
  ApiKeyCreated,
  createApiKey,
  listApiKeys,
  revokeApiKey,
} from "./api";
import { formatDate } from "@/lib/utils";

export function ApiKeysPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: listApiKeys });

  const [name, setName] = useState("");
  const [justCreated, setJustCreated] = useState<ApiKeyCreated | null>(null);

  const create = useMutation({
    mutationFn: createApiKey,
    onSuccess: (k) => {
      setJustCreated(k);
      setName("");
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (e) =>
      toast.push({
        title: "Create failed",
        description: (e as Error).message,
        tone: "error",
      }),
  });

  const revoke = useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => {
      toast.push({ title: "Key revoked", tone: "success" });
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (e) =>
      toast.push({
        title: "Revoke failed",
        description: (e as Error).message,
        tone: "error",
      }),
  });

  const onCreate = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    create.mutate(trimmed);
  };

  const onRevoke = (id: string, keyName: string) => {
    if (!confirm(`Revoke key "${keyName}"? Anything using it will stop working.`)) return;
    revoke.mutate(id);
  };

  const onCopy = async (token: string) => {
    try {
      await navigator.clipboard.writeText(token);
      toast.push({ title: "Copied to clipboard", tone: "success" });
    } catch {
      toast.push({ title: "Copy failed", tone: "error" });
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">API keys</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Personal access tokens for the REST API. Use them in the
          <code className="px-1 mx-1 bg-muted rounded text-xs">X-Api-Key: …</code>
          header for service-to-service calls.
        </p>
      </div>

      {/* Reveal banner — shown only right after creation */}
      {justCreated && (
        <Card className="border-amber-300 bg-amber-50">
          <CardHeader>
            <CardTitle>Save this key now</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            <p className="text-sm text-amber-900">
              This is the only time the full key will be shown. Copy it and store it somewhere safe.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 font-mono text-xs bg-white border border-amber-200 rounded px-2 py-2 break-all">
                {justCreated.key}
              </code>
              <Button size="sm" onClick={() => onCopy(justCreated.key)}>
                Copy
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setJustCreated(null)}
              >
                Done
              </Button>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Create form */}
      <Card>
        <CardHeader>
          <CardTitle>Create a new key</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1 min-w-[240px] space-y-1">
              <label className="text-xs font-medium">Name (for your reference)</label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="CI runner / local dev / Postman"
                onKeyDown={(e) => {
                  if (e.key === "Enter") onCreate();
                }}
              />
            </div>
            <Button onClick={onCreate} disabled={!name.trim() || create.isPending}>
              {create.isPending ? "Creating…" : "Create key"}
            </Button>
          </div>
        </CardBody>
      </Card>

      {/* Key list */}
      <Card>
        <CardHeader>
          <CardTitle>Your keys</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          {keys.isLoading ? (
            <div className="p-4 space-y-2">
              <Skeleton className="h-8" />
              <Skeleton className="h-8" />
            </div>
          ) : !keys.data || keys.data.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground text-center">
              No keys yet.
            </div>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Name</TH>
                  <TH>Status</TH>
                  <TH>Created</TH>
                  <TH>Last used</TH>
                  <TH></TH>
                </TR>
              </THead>
              <TBody>
                {keys.data.map((k) => {
                  const revoked = !!k.revoked_at;
                  return (
                    <TR key={k.id}>
                      <TD className="font-medium">{k.name}</TD>
                      <TD>
                        <Badge tone={revoked ? "danger" : "success"}>
                          {revoked ? "Revoked" : "Active"}
                        </Badge>
                      </TD>
                      <TD className="text-xs text-muted-foreground">
                        {formatDate(k.created_at)}
                      </TD>
                      <TD className="text-xs text-muted-foreground">
                        {k.last_used_at ? formatDate(k.last_used_at) : "Never"}
                      </TD>
                      <TD>
                        {!revoked && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => onRevoke(k.id, k.name)}
                            disabled={revoke.isPending}
                          >
                            Revoke
                          </Button>
                        )}
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
