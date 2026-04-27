import * as React from "react";
import { create } from "zustand";
import { cn } from "@/lib/utils";

interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone?: "info" | "success" | "error";
}

interface ToastStore {
  items: ToastItem[];
  push: (item: Omit<ToastItem, "id">) => void;
  remove: (id: number) => void;
}

let nextId = 1;

export const useToast = create<ToastStore>((set) => ({
  items: [],
  push: (item) =>
    set((state) => ({
      items: [...state.items, { id: nextId++, ...item }],
    })),
  remove: (id) =>
    set((state) => ({ items: state.items.filter((i) => i.id !== id) })),
}));

export function ToastViewport() {
  const items = useToast((s) => s.items);
  const remove = useToast((s) => s.remove);
  React.useEffect(() => {
    if (!items.length) return;
    const timers = items.map((i) =>
      window.setTimeout(() => remove(i.id), 4500),
    );
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [items, remove]);

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 w-80">
      {items.map((t) => (
        <div
          key={t.id}
          className={cn(
            "rounded-md border border-border bg-background px-4 py-3 shadow-md",
            t.tone === "success" && "border-emerald-300",
            t.tone === "error" && "border-red-300",
          )}
        >
          <div className="text-sm font-medium">{t.title}</div>
          {t.description && (
            <div className="text-xs text-muted-foreground mt-1">{t.description}</div>
          )}
        </div>
      ))}
    </div>
  );
}
