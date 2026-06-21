import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import {
  createProviderKey,
  ApiKeyCreated,
  createApiKey,
  listProviderKeys,
  listApiKeys,
  updateMe,
  updateProviderKey,
  revokeApiKey,
  revokeProviderKey,
} from "./api";
import { useCurrentUser } from "./hooks";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { ProviderKeyCreated, ProviderName } from "@/lib/api/types";

type ProviderCardConfig = {
  id: ProviderName;
  title: string;
  description: string;
  accent: string;
  iconSrc: string;
};

const PROVIDERS: ProviderCardConfig[] = [
  {
    id: "groq",
    title: "Groq",
    description: "Ultra-low latency for fast interactive completions.",
    accent: "from-cyan-500/20 to-sky-500/10",
    iconSrc: "/groq.png",
  },
  {
    id: "gemini",
    title: "Gemini",
    description: "Google models for broad coverage and long context.",
    accent: "from-emerald-500/20 to-teal-500/10",
    iconSrc: "/gemini.png",
  },
  {
    id: "mistral",
    title: "Mistral",
    description: "Sharp general-purpose models with strong reasoning.",
    accent: "from-orange-500/20 to-amber-500/10",
    iconSrc: "/mistral.png",
  },
  {
    id: "deepseek",
    title: "DeepSeek",
    description: "Efficient reasoning models for budget-aware usage.",
    accent: "from-indigo-500/20 to-violet-500/10",
    iconSrc: "/deepseek.png",
  },
];

function ProviderMark({ provider, className }: { provider: ProviderCardConfig; className?: string }) {
  return (
    <img
      src={provider.iconSrc}
      alt={`${provider.title} logo`}
      className={cn("h-8 w-8 rounded-lg object-contain", className)}
    />
  );
}

function ProviderKeyCard({
  provider,
  keys,
  onCreate,
  onToggle,
  onDelete,
  justCreated,
  onClearJustCreated,
  busy,
}: {
  provider: ProviderCardConfig;
  keys: Array<{
    id: string;
    label: string;
    key_tail: string;
    is_enabled: boolean;
    created_at: string;
    last_used_at: string | null;
    revoked_at: string | null;
    provider: ProviderName;
  }>;
  onCreate: (provider: ProviderName, label: string, apiKey: string, isEnabled: boolean) => void;
  onToggle: (id: string, label: string, isEnabled: boolean) => void;
  onDelete: (id: string, label: string) => void;
  justCreated: ProviderKeyCreated | null;
  onClearJustCreated: () => void;
  busy: boolean;
}) {
  const [label, setLabel] = useState(`${provider.title} key`);
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    setLabel(`${provider.title} key`);
  }, [provider.title]);

  const activeCount = keys.filter((key) => key.is_enabled && !key.revoked_at).length;

  return (
    <Card className={cn("overflow-hidden border-border/70", `bg-gradient-to-br ${provider.accent}`)}>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-background/90 shadow-sm">
            <ProviderMark provider={provider} />
          </div>
          <div>
            <CardTitle>{provider.title}</CardTitle>
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">{provider.description}</p>
          </div>
        </div>
        <div className="text-right text-xs text-muted-foreground">
          {activeCount} active key{activeCount === 1 ? "" : "s"}
        </div>
      </CardHeader>
      <CardBody className="space-y-4 bg-background/90">
        {justCreated && justCreated.provider === provider.id && (
          <Card className="border-amber-300 bg-amber-50">
            <CardBody className="space-y-3">
              <div className="text-sm font-medium text-amber-950">Save this key now</div>
              <p className="text-sm text-amber-900">
                This is the only time the full API key is shown. Copy it before you leave this page.
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <code className="flex-1 rounded border border-amber-200 bg-white px-3 py-2 font-mono text-xs break-all">
                  {justCreated.api_key}
                </code>
                <Button size="sm" onClick={async () => navigator.clipboard.writeText(justCreated.api_key)}>
                  Copy
                </Button>
                <Button size="sm" variant="outline" onClick={onClearJustCreated}>
                  Done
                </Button>
              </div>
            </CardBody>
          </Card>
        )}

        <div className="grid gap-3 lg:grid-cols-[1.1fr_1.4fr_auto]">
          <div className="space-y-1">
            <label className="text-xs font-medium">Key label</label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Prod / Sandbox / CI" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium">API key</label>
            <Input
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              type="password"
              placeholder="Paste the provider API key"
              autoComplete="off"
            />
          </div>
          <div className="flex items-end gap-2">
            <label className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="h-4 w-4"
              />
              Active
            </label>
            <Button
              disabled={busy || !label.trim() || !apiKey.trim()}
              onClick={() => {
                onCreate(provider.id, label.trim(), apiKey.trim(), enabled);
                setApiKey("");
              }}
            >
              Save key
            </Button>
          </div>
        </div>

        {keys.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-background/60 p-4 text-sm text-muted-foreground">
            No keys saved for {provider.title} yet.
          </div>
        ) : (
          <div className="space-y-2">
            {keys.map((key) => {
              const revoked = !!key.revoked_at;
              return (
                <div
                  key={key.id}
                  className="flex flex-col gap-3 rounded-lg border border-border bg-background p-4 lg:flex-row lg:items-center lg:justify-between"
                >
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium">{key.label}</div>
                      <Badge tone={revoked ? "danger" : key.is_enabled ? "success" : "default"}>
                        {revoked ? "Revoked" : key.is_enabled ? "Active" : "Off"}
                      </Badge>
                    </div>
                    <div className="font-mono text-xs text-muted-foreground">****{key.key_tail}</div>
                    <div className="text-xs text-muted-foreground">
                      Created {formatDate(key.created_at)}
                      {key.last_used_at ? ` · Last used ${formatDate(key.last_used_at)}` : ""}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {!revoked && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onToggle(key.id, key.label, !key.is_enabled)}
                        disabled={busy}
                      >
                        {key.is_enabled ? "Turn off" : "Turn on"}
                      </Button>
                    )}
                    {!revoked && (
                      <Button size="sm" variant="destructive" onClick={() => onDelete(key.id, key.label)} disabled={busy}>
                        Delete
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function useProviderKeyGroups() {
  const providerKeys = useQuery({ queryKey: ["provider-keys"], queryFn: listProviderKeys });
  return providerKeys;
}

export function SettingsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: me } = useCurrentUser();
  const providerKeys = useProviderKeyGroups();
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: listApiKeys });
  const providerKeyGroups = useMemo(() => {
    const grouped: Record<ProviderName, NonNullable<typeof providerKeys.data>> = {
      groq: [],
      gemini: [],
      mistral: [],
      deepseek: [],
    };
    for (const key of providerKeys.data ?? []) {
      grouped[key.provider].push(key);
    }
    return grouped;
  }, [providerKeys.data]);

  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [name, setName] = useState("");
  const [justCreated, setJustCreated] = useState<ApiKeyCreated | null>(null);
  const [justCreatedProviderKey, setJustCreatedProviderKey] = useState<ProviderKeyCreated | null>(null);

  useEffect(() => {
    if (!me) return;
    setEmail(me.email);
    setDisplayName(me.display_name);
  }, [me]);

  const profile = useMutation({
    mutationFn: ({ email: nextEmail, displayName: nextDisplayName }: { email: string; displayName: string }) =>
      updateMe(nextEmail, nextDisplayName),
    onSuccess: (updated) => {
      toast.push({ title: "Profile updated", tone: "success" });
      setEmail(updated.email);
      setDisplayName(updated.display_name);
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
    onError: (e) =>
      toast.push({
        title: "Update failed",
        description: (e as Error).message,
        tone: "error",
      }),
  });

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

  const createProvider = useMutation({
    mutationFn: createProviderKey,
    onSuccess: (k) => {
      setJustCreatedProviderKey(k);
      qc.invalidateQueries({ queryKey: ["provider-keys"] });
    },
    onError: (e) =>
      toast.push({
        title: "Provider key save failed",
        description: (e as Error).message,
        tone: "error",
      }),
  });

  const updateProvider = useMutation({
    mutationFn: ({ id, label, isEnabled }: { id: string; label: string; isEnabled: boolean }) =>
      updateProviderKey(id, { label, isEnabled }),
    onSuccess: () => {
      toast.push({ title: "Provider key updated", tone: "success" });
      qc.invalidateQueries({ queryKey: ["provider-keys"] });
    },
    onError: (e) =>
      toast.push({
        title: "Update failed",
        description: (e as Error).message,
        tone: "error",
      }),
  });

  const revokeProvider = useMutation({
    mutationFn: revokeProviderKey,
    onSuccess: () => {
      toast.push({ title: "Provider key deleted", tone: "success" });
      qc.invalidateQueries({ queryKey: ["provider-keys"] });
    },
    onError: (e) =>
      toast.push({
        title: "Delete failed",
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

  const providerBusy = createProvider.isPending || updateProvider.isPending || revokeProvider.isPending;

  const onSaveProfile = () => {
    const trimmedEmail = email.trim();
    const trimmedName = displayName.trim();
    if (!trimmedEmail || !trimmedName) return;
    profile.mutate({ email: trimmedEmail, displayName: trimmedName });
  };

  const onCreateProviderKey = (
    provider: ProviderName,
    label: string,
    apiKey: string,
    isEnabled: boolean,
  ) => {
    createProvider.mutate({ provider, label, apiKey, isEnabled });
  };

  const onToggleProviderKey = (id: string, label: string, isEnabled: boolean) => {
    updateProvider.mutate({ id, label, isEnabled });
  };

  const onDeleteProviderKey = (id: string, label: string) => {
    if (!confirm(`Delete key "${label}"? It will stop working immediately.`)) return;
    revokeProvider.mutate(id);
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(15,23,42,0.08),_transparent_38%),linear-gradient(180deg,_rgba(248,250,252,1),_rgba(255,255,255,1))] p-6 md:p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="space-y-2">
          <div className="inline-flex items-center rounded-full border border-border bg-background/80 px-3 py-1 text-xs font-medium text-muted-foreground shadow-sm">
            Account settings
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">Personal details and LLM provider keys</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Update your profile once, store provider keys securely, and choose which key is active for each model vendor.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
              <div className="space-y-1">
                <label className="text-xs font-medium">Display name</label>
                <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Your name" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium">Email</label>
                <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
              </div>
              <Button onClick={onSaveProfile} disabled={!email.trim() || !displayName.trim() || profile.isPending}>
                {profile.isPending ? "Saving…" : "Save profile"}
              </Button>
            </div>
            <div className="mt-3 text-xs text-muted-foreground">
              Signed in as <span className="font-medium text-foreground">{me?.email ?? "..."}</span>
            </div>
          </CardBody>
        </Card>

        <div className="space-y-4">
          <div>
            <h2 className="text-xl font-semibold">LLM provider keys</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Save multiple keys for each provider and keep only one active at a time.
            </p>
          </div>

          {PROVIDERS.map((provider) => (
            <ProviderKeyCard
              key={provider.id}
              provider={provider}
              keys={providerKeyGroups[provider.id] ?? []}
              onCreate={onCreateProviderKey}
              onToggle={onToggleProviderKey}
              onDelete={onDeleteProviderKey}
              justCreated={justCreatedProviderKey}
              onClearJustCreated={() => setJustCreatedProviderKey(null)}
              busy={providerBusy}
            />
          ))}
        </div>

        {/* Legacy REST API keys remain available for app integrations. */}
        <div className="space-y-4">
          <div>
            <h2 className="text-xl font-semibold">Personal API keys</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              These keys still work for REST and service-to-service access.
            </p>
          </div>

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
                  <Button size="sm" variant="outline" onClick={() => setJustCreated(null)}>
                    Done
                  </Button>
                </div>
              </CardBody>
            </Card>
          )}

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
                <div className="p-6 text-sm text-muted-foreground text-center">No keys yet.</div>
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
                          <TD className="text-xs text-muted-foreground">{formatDate(k.created_at)}</TD>
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
      </div>
    </div>
  );
}

export const ApiKeysPage = SettingsPage;
