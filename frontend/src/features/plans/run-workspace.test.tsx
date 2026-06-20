import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CheckpointCard } from "./run-workspace";
import type { CheckpointResponse } from "@/lib/api/types";

const checkpoint: CheckpointResponse = {
  job_id: "job_123",
  paused_at: "extractor",
  state: {
    requirements: [
      {
        id: "REQ-1",
        kind: "functional",
        priority: 3,
        title: "Authentication",
        statement: "The system shall require MFA for administrators.",
      },
    ],
  },
};

describe("CheckpointCard", () => {
  it("exposes accept, reprompt, and abort controls", async () => {
    const user = userEvent.setup();
    const onAccept = vi.fn();
    const onReprompt = vi.fn();
    const onAbort = vi.fn();

    render(
      <CheckpointCard
        checkpoint={checkpoint}
        actionPending={false}
        onAccept={onAccept}
        onReprompt={onReprompt}
        onAbort={onAbort}
      />,
    );

    await user.click(screen.getByRole("button", { name: /accept and continue/i }));
    expect(onAccept).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: /send feedback and re-run/i }));
    await user.type(
      screen.getByPlaceholderText(/focus on cybersecurity edge cases/i),
      "Add negative MFA bypass cases.",
    );
    await user.click(screen.getByRole("button", { name: /^send feedback$/i }));
    expect(onReprompt).toHaveBeenCalledWith("Add negative MFA bypass cases.");

    await user.click(screen.getByRole("button", { name: /abort run/i }));
    expect(onAbort).toHaveBeenCalledTimes(1);
  });
});
