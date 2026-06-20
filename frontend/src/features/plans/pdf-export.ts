import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import type { TestPlan, TestPlanSummary, TestCaseSummary } from "@/lib/api/types";

const MARGIN = 14;
const PAGE_WIDTH = 210; // A4 portrait, mm
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2;

function riskLabel(level: number): string {
  if (level >= 4) return "Critical";
  if (level >= 3) return "High";
  if (level >= 2) return "Medium";
  return "Low";
}

function riskColor(level: number): [number, number, number] {
  if (level >= 3) return [220, 38, 38];   // red
  if (level === 2) return [217, 119, 6];  // amber
  return [37, 99, 235];                    // blue
}

interface Cursor {
  doc: jsPDF;
  y: number;
}

function ensureSpace(c: Cursor, needed: number): void {
  const pageHeight = c.doc.internal.pageSize.getHeight();
  if (c.y + needed > pageHeight - MARGIN) {
    c.doc.addPage();
    c.y = MARGIN;
  }
}

function heading(c: Cursor, text: string, size = 14): void {
  ensureSpace(c, 12);
  c.doc.setFont("helvetica", "bold");
  c.doc.setFontSize(size);
  c.doc.setTextColor(20, 20, 20);
  c.doc.text(text, MARGIN, c.y);
  c.y += size * 0.5 + 2;
  // underline
  c.doc.setDrawColor(180, 180, 180);
  c.doc.line(MARGIN, c.y, PAGE_WIDTH - MARGIN, c.y);
  c.y += 4;
}

function paragraph(c: Cursor, text: string, opts?: { italic?: boolean; muted?: boolean }): void {
  if (!text) return;
  c.doc.setFont("helvetica", opts?.italic ? "italic" : "normal");
  c.doc.setFontSize(10);
  c.doc.setTextColor(opts?.muted ? 100 : 30, opts?.muted ? 100 : 30, opts?.muted ? 100 : 30);
  const lines = c.doc.splitTextToSize(text, CONTENT_WIDTH) as string[];
  for (const line of lines) {
    ensureSpace(c, 5);
    c.doc.text(line, MARGIN, c.y);
    c.y += 5;
  }
  c.y += 1;
}

function bulletList(c: Cursor, items: string[]): void {
  if (items.length === 0) return;
  c.doc.setFont("helvetica", "normal");
  c.doc.setFontSize(10);
  c.doc.setTextColor(30, 30, 30);
  for (const item of items) {
    const lines = c.doc.splitTextToSize(item, CONTENT_WIDTH - 6) as string[];
    for (let i = 0; i < lines.length; i++) {
      ensureSpace(c, 5);
      const prefix = i === 0 ? "•  " : "    ";
      c.doc.text(prefix + lines[i], MARGIN, c.y);
      c.y += 5;
    }
  }
  c.y += 1;
}

function subheading(c: Cursor, text: string): void {
  ensureSpace(c, 8);
  c.doc.setFont("helvetica", "bold");
  c.doc.setFontSize(11);
  c.doc.setTextColor(60, 60, 60);
  c.doc.text(text.toUpperCase(), MARGIN, c.y);
  c.y += 5;
}

function field(c: Cursor, label: string, value: string): void {
  if (!value) return;
  ensureSpace(c, 6);
  c.doc.setFont("helvetica", "bold");
  c.doc.setFontSize(9);
  c.doc.setTextColor(80, 80, 80);
  c.doc.text(label, MARGIN, c.y);

  c.doc.setFont("helvetica", "normal");
  c.doc.setTextColor(30, 30, 30);
  const labelWidth = c.doc.getTextWidth(label);
  const lines = c.doc.splitTextToSize(value, CONTENT_WIDTH - labelWidth - 2) as string[];
  c.doc.text(lines[0], MARGIN + labelWidth + 2, c.y);
  c.y += 5;
  for (let i = 1; i < lines.length; i++) {
    ensureSpace(c, 5);
    c.doc.text(lines[i], MARGIN, c.y);
    c.y += 5;
  }
}

type ExportablePlan = TestPlanSummary | TestPlan;

function planTestCaseCount(plan: ExportablePlan): number {
  return plan.n_test_cases ?? plan.test_cases.length;
}

function planVersionLabel(plan: ExportablePlan): string | null {
  if (!plan.version) return null;
  return plan.version.startsWith("v") ? plan.version : `v${plan.version}`;
}

function pageFooter(doc: jsPDF, plan: ExportablePlan): void {
  const pageCount = doc.getNumberOfPages();
  for (let p = 1; p <= pageCount; p++) {
    doc.setPage(p);
    const pageHeight = doc.internal.pageSize.getHeight();
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(140, 140, 140);
    const version = planVersionLabel(plan);
    doc.text(
      `${plan.title}${version ? ` - ${version}` : ""}`,
      MARGIN,
      pageHeight - 8,
    );
    doc.text(`Page ${p} / ${pageCount}`, PAGE_WIDTH - MARGIN, pageHeight - 8, {
      align: "right",
    });
  }
}

export function exportPlanToPdf(
  plan: ExportablePlan,
  coverage?: Record<string, string[]>,
): void {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const c: Cursor = { doc, y: MARGIN };

  // ---- Cover header
  doc.setFont("helvetica", "bold");
  doc.setFontSize(20);
  doc.setTextColor(20, 20, 20);
  doc.text(plan.title, MARGIN, c.y + 4);
  c.y += 12;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  doc.setTextColor(110, 110, 110);
  const metaLine = [
    planVersionLabel(plan) ? `Version ${planVersionLabel(plan)}` : null,
    plan.author ? `Author: ${plan.author}` : null,
    `${planTestCaseCount(plan)} test case${planTestCaseCount(plan) === 1 ? "" : "s"}`,
    `Generated ${new Date().toLocaleDateString()}`,
  ]
    .filter(Boolean)
    .join("    |    ");
  doc.text(metaLine, MARGIN, c.y);
  c.y += 8;
  doc.setDrawColor(150, 150, 150);
  doc.line(MARGIN, c.y, PAGE_WIDTH - MARGIN, c.y);
  c.y += 6;

  // ---- Introduction
  if (plan.introduction) {
    heading(c, "1. Introduction");
    paragraph(c, plan.introduction);
  }

  // ---- Objectives
  if (plan.objectives && plan.objectives.length > 0) {
    heading(c, "2. Objectives");
    bulletList(c, plan.objectives);
  }

  // ---- Scope
  heading(c, "3. Scope");
  if (plan.scope) paragraph(c, plan.scope);
  if (plan.out_of_scope && plan.out_of_scope.length > 0) {
    subheading(c, "Out of scope");
    bulletList(c, plan.out_of_scope);
  }

  // ---- Strategy
  if (plan.strategy) {
    heading(c, "4. Test strategy");
    paragraph(c, plan.strategy);
  }

  // ---- Entry / Exit criteria
  if (
    (plan.entry_criteria && plan.entry_criteria.length > 0) ||
    (plan.exit_criteria && plan.exit_criteria.length > 0)
  ) {
    heading(c, "5. Entry & exit criteria");
    if (plan.entry_criteria && plan.entry_criteria.length > 0) {
      subheading(c, "Entry criteria");
      bulletList(c, plan.entry_criteria);
    }
    if (plan.exit_criteria && plan.exit_criteria.length > 0) {
      subheading(c, "Exit criteria");
      bulletList(c, plan.exit_criteria);
    }
  }

  // ---- Risks
  if (plan.risks && plan.risks.length > 0) {
    heading(c, "6. Risks");
    bulletList(c, plan.risks);
  }

  // ---- Coverage
  if (coverage && Object.keys(coverage).length > 0) {
    heading(c, "7. Requirement coverage");
    const total = Object.keys(coverage).length;
    const covered = Object.values(coverage).filter((v) => v.length > 0).length;
    const pct = total === 0 ? 0 : Math.round((covered / total) * 100);
    paragraph(c, `${covered} of ${total} requirements covered (${pct}%).`);
    autoTable(doc, {
      startY: c.y,
      margin: { left: MARGIN, right: MARGIN },
      head: [["Requirement", "Test cases"]],
      body: Object.entries(coverage).map(([rid, tcs]) => [
        rid,
        tcs.length === 0 ? "— uncovered —" : tcs.join(", "),
      ]),
      styles: { fontSize: 9, cellPadding: 2 },
      headStyles: { fillColor: [240, 240, 240], textColor: 30, fontStyle: "bold" },
      didParseCell: (data) => {
        if (data.section === "body" && data.column.index === 1) {
          if (typeof data.cell.text[0] === "string" && data.cell.text[0].includes("uncovered")) {
            data.cell.styles.textColor = [200, 30, 30];
            data.cell.styles.fontStyle = "italic";
          }
        }
      },
    });
    c.y = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 4;
  }

  // ---- Test case overview table
  doc.addPage();
  c.y = MARGIN;
  heading(c, "8. Test cases — overview");

  const overviewBody = plan.test_cases.map((tc, i) => [
    `TC-${String(i + 1).padStart(3, "0")}`,
    tc.title,
    riskLabel(tc.risk_level),
    tc.requirement_ids.join(", ") || "—",
    (tc.testing_types ?? []).join(", ") || "—",
    tc.estimated_duration_minutes ? `${tc.estimated_duration_minutes} min` : "—",
    tc.assignee ?? "—",
  ]);

  autoTable(doc, {
    startY: c.y,
    margin: { left: MARGIN, right: MARGIN },
    head: [["ID", "Title", "Risk", "Requirements", "Testing types", "Duration", "Assignee"]],
    body: overviewBody,
    styles: { fontSize: 8, cellPadding: 2, overflow: "linebreak" },
    headStyles: { fillColor: [50, 65, 90], textColor: 255, fontStyle: "bold" },
    columnStyles: {
      0: { cellWidth: 16, fontStyle: "bold" },
      1: { cellWidth: 50 },
      2: { cellWidth: 16 },
      3: { cellWidth: 30, font: "courier", fontSize: 7 },
      4: { cellWidth: 30 },
      5: { cellWidth: 18 },
      6: { cellWidth: 22 },
    },
    didParseCell: (data) => {
      if (data.section === "body" && data.column.index === 2) {
        const tc = plan.test_cases[data.row.index];
        if (tc) {
          const [r, g, b] = riskColor(tc.risk_level);
          data.cell.styles.textColor = [r, g, b];
          data.cell.styles.fontStyle = "bold";
        }
      }
    },
  });
  c.y = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 6;

  // ---- Per-test-case detail
  doc.addPage();
  c.y = MARGIN;
  heading(c, "9. Test cases — detail");

  plan.test_cases.forEach((tc, i) => {
    renderTestCaseDetail(c, tc, i + 1);
  });

  pageFooter(doc, plan);
  doc.save(`${plan.id}.pdf`);
}

function renderTestCaseDetail(c: Cursor, tc: TestCaseSummary, idx: number): void {
  ensureSpace(c, 18);

  // Title bar
  c.doc.setFillColor(245, 247, 250);
  c.doc.rect(MARGIN, c.y, CONTENT_WIDTH, 8, "F");
  c.doc.setFont("helvetica", "bold");
  c.doc.setFontSize(11);
  c.doc.setTextColor(20, 20, 20);
  c.doc.text(`TC-${String(idx).padStart(3, "0")}  ${tc.title}`, MARGIN + 2, c.y + 5.5);

  // Risk pill on right
  const [r, g, b] = riskColor(tc.risk_level);
  c.doc.setFillColor(r, g, b);
  const pillW = 22;
  c.doc.roundedRect(PAGE_WIDTH - MARGIN - pillW - 1, c.y + 1.5, pillW, 5, 1.5, 1.5, "F");
  c.doc.setFont("helvetica", "bold");
  c.doc.setFontSize(8);
  c.doc.setTextColor(255, 255, 255);
  c.doc.text(riskLabel(tc.risk_level), PAGE_WIDTH - MARGIN - pillW / 2 - 1, c.y + 5, {
    align: "center",
  });
  c.y += 11;

  // Objective
  field(c, "Objective: ", tc.objective);
  if (tc.risk_description) field(c, "Risk: ", tc.risk_description);
  field(c, "Requirements: ", tc.requirement_ids.join(", ") || "—");
  if (tc.source_evidence && tc.source_evidence.length > 0) {
    subheading(c, "Source evidence");
    bulletList(
      c,
      tc.source_evidence.map((ev) => {
        const page = ev.page_start
          ? ` p.${ev.page_start}${ev.page_end && ev.page_end !== ev.page_start ? `-${ev.page_end}` : ""}`
          : "";
        return `${ev.relation}: ${ev.document_id} / ${ev.chunk_id}${page} - ${ev.excerpt}`;
      }),
    );
  }
  if (tc.testing_types && tc.testing_types.length > 0) {
    field(c, "Testing types: ", tc.testing_types.join(", "));
  }
  if (tc.estimated_duration_minutes) {
    field(c, "Duration: ", `${tc.estimated_duration_minutes} min`);
  }
  if (tc.assignee) field(c, "Assignee: ", tc.assignee);

  if (tc.steps && tc.steps.length > 0) {
    subheading(c, "Steps");
    const lines = tc.steps.map(
      (s, i) => `${i + 1}. ${s.action} → ${s.expected_result}${s.notes ? ` (${s.notes})` : ""}`,
    );
    bulletList(c, lines);
  }

  if (tc.acceptance_criteria && tc.acceptance_criteria.length > 0) {
    subheading(c, "Acceptance criteria");
    const lines = tc.acceptance_criteria.map((ac) => {
      const suffix = ac.tolerance ? ` [${ac.tolerance}]` : "";
      const tag = ac.measurable ? "" : " (qualitative)";
      return `${ac.statement}${suffix}${tag}`;
    });
    bulletList(c, lines);
  }

  if (tc.deliverables && tc.deliverables.length > 0) {
    subheading(c, "Deliverables");
    bulletList(c, tc.deliverables);
  }

  if (tc.dependencies && tc.dependencies.length > 0) {
    subheading(c, "Dependencies");
    bulletList(c, tc.dependencies);
  }

  if (tc.kpis && tc.kpis.length > 0) {
    subheading(c, "KPIs");
    bulletList(c, tc.kpis);
  }

  if (tc.features_not_tested && tc.features_not_tested.length > 0) {
    subheading(c, "Features not tested");
    bulletList(c, tc.features_not_tested);
  }

  c.y += 4;
}
