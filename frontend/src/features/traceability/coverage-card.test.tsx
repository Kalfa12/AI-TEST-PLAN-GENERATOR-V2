import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectCoverageCard } from "./coverage-card";
import { getProjectCoverage, getProjectGaps } from "./api";

vi.mock("./api", () => ({
  getProjectCoverage: vi.fn(),
  getProjectGaps: vi.fn(),
}));

function renderWithQueryClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ProjectCoverageCard", () => {
  it("renders coverage percentage and uncovered requirement ids", async () => {
    vi.mocked(getProjectCoverage).mockResolvedValue({
      "REQ-1": ["TC-1"],
      "REQ-2": [],
      "REQ-3": ["TC-2"],
    });
    vi.mocked(getProjectGaps).mockResolvedValue({
      project_id: "project-a",
      uncovered_requirement_ids: ["REQ-2"],
    });

    renderWithQueryClient(<ProjectCoverageCard projectId="project-a" />);

    expect(await screen.findByText("67%")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/\/ 3 requirements covered/i)).toBeInTheDocument();
    expect(screen.getByText("Uncovered (1)")).toBeInTheDocument();
    expect(screen.getByText("REQ-2")).toBeInTheDocument();
  });
});
