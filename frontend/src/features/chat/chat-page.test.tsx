import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageBubble } from "./chat-page";
import type { Message } from "./chat-page";

describe("MessageBubble", () => {
  it("shows an explicit notice when the assistant returns an unsupported action", () => {
    const message: Message = {
      id: "msg-1",
      role: "assistant",
      text: "I can explain the change, but cannot apply it here.",
      unsupportedAction: "bulk_plan_rewrite",
    };

    render(<MessageBubble message={message} onConfirm={vi.fn()} />);

    expect(
      screen.getByText("Action not available: bulk_plan_rewrite"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/persisted plan edits must go through the generation workflow/i),
    ).toBeInTheDocument();
  });
});
