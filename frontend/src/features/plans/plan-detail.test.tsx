import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SourceEvidenceList } from "./plan-detail";
import type { SourceEvidence } from "@/lib/api/types";

describe("SourceEvidenceList", () => {
  it("renders traceable document, chunk, page, relation, and excerpt evidence", () => {
    const evidence: SourceEvidence[] = [
      {
        relation: "verifies",
        document_id: "doc-auth-spec",
        chunk_id: "chunk-007",
        page_start: 4,
        page_end: 5,
        excerpt: "Administrative sessions shall require MFA reauthentication.",
      },
    ];

    render(<SourceEvidenceList evidence={evidence} />);

    expect(screen.getByText("verifies")).toBeInTheDocument();
    expect(screen.getByText("doc-auth-spec")).toBeInTheDocument();
    expect(screen.getByText("chunk-007")).toBeInTheDocument();
    expect(screen.getByText("p.4-5")).toBeInTheDocument();
    expect(
      screen.getByText("Administrative sessions shall require MFA reauthentication."),
    ).toBeInTheDocument();
  });
});
