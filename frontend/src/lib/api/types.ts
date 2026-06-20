// Hand-typed mirrors of backend response shapes.
// The full client is auto-generated into ./generated/ via `npm run gen:api`.
// These thin types are used by hooks so the rest of the app does not depend
// on the generated client's exact module layout (which can change between
// codegen versions).

export interface User {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
  is_active: boolean;
  is_admin?: boolean;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  created_at: string;
  archived_at?: string | null;
  owner_id?: string | null;
  monthly_budget_usd: number;
  budget_override_until?: string | null;
  budget_override_usd?: number | null;
  current_month_spend_usd: number;
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
}

export interface DocumentItem {
  id: string;
  title: string;
  kind: string;
  scope: string;
  n_chunks: number;
  ingested_at: string;
  source_uri: string;
}

export interface DocumentListResponse {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentUploadAccepted {
  job_id: string;
  document_id: string | null;
  message: string;
}

export interface PlanListItem {
  id: string;
  title: string;
  detail_level: string;
  n_test_cases: number;
}

export interface PlanListResponse {
  items: PlanListItem[];
  total: number;
}

export interface TestStep {
  id: string;
  index: number;
  action: string;
  expected_result: string;
  notes?: string | null;
}

export interface AcceptanceCriterion {
  id: string;
  statement: string;
  measurable: boolean;
  tolerance?: string | null;
}

export interface SourceEvidence {
  chunk_id: string;
  document_id: string;
  page_start?: number | null;
  page_end?: number | null;
  excerpt: string;
  relation: string;
}

export type TestCaseStatus =
  | "not_started"
  | "planned"
  | "running"
  | "blocked"
  | "passed"
  | "failed";

export interface TestCaseSummary {
  id: string;
  title: string;
  objective: string;
  requirement_ids: string[];
  risk_level: number;
  risk_description?: string | null;
  estimated_duration_minutes: number | null;
  tags: string[];
  testing_types?: string[];
  features_not_tested?: string[];
  deliverables?: string[];
  dependencies?: string[];
  kpis?: string[];
  assignee?: string | null;
  status?: TestCaseStatus;
  status_note?: string | null;
  steps?: TestStep[];
  acceptance_criteria?: AcceptanceCriterion[];
  source_evidence?: SourceEvidence[];
}

export interface Resource {
  id: string;
  project_id?: string | null;
  name: string;
  service: string;
  role?: string | null;
  availability_pct: number;
}

export interface ResourceListResponse {
  items: Resource[];
  total: number;
}

export interface Milestone {
  id: string;
  name: string;
  due: string;
  gate: boolean;
  depends_on: string[];
}

export interface ScheduledAssignment {
  start: string;
  end: string;
  resource_ids: string[];
  service?: string | null;
}

export interface TestSchedule {
  plan_id: string;
  milestones: Milestone[];
  assignments: Record<string, ScheduledAssignment>;
}

export interface TestPlanSummary {
  id: string;
  project_id: string | null;
  title: string;
  version?: string;
  author?: string;
  detail_level: string;
  introduction?: string;
  objectives?: string[];
  scope: string;
  out_of_scope?: string[];
  strategy: string;
  n_test_cases: number;
  test_cases: TestCaseSummary[];
  entry_criteria?: string[];
  exit_criteria?: string[];
  risks?: string[];
  schedule?: TestSchedule | null;
}

export type TestPlan = Omit<TestPlanSummary, "n_test_cases"> & {
  n_test_cases?: number;
};

export interface CoverageMatrixResponse {
  plan_id: string;
  matrix: Record<string, string[]>;
}

export interface CreatePlanAccepted {
  job_id: string;
  session_id: string;
  message: string;
}

export interface ChatReply {
  session_id: string;
  assistant_message: string;
  pending_action: string | null;
  pending_action_id?: string | null;
  pending_action_preview?: string | null;
  unsupported_action?: string | null;
}

export interface DeadLetterEntry {
  job_id: string;
  task_name: string;
  error: string;
  failed_at: string;
  job_kwargs: Record<string, unknown>;
}

export interface DeadLetterListResponse {
  items: DeadLetterEntry[];
  total: number;
}

export interface CostSummaryRow {
  bucket: string;
  total_usd: number;
  prompt_tokens: number;
  completion_tokens: number;
  call_count: number;
  [key: string]: unknown;
}

export interface TraceNode {
  id: string;
  type: string | null;
  attributes: Record<string, unknown>;
}

export interface TraceEdge {
  source: string;
  target: string;
  kind: string;
  confidence: number;
}

export interface LineageResponse {
  root: TraceNode;
  edges: TraceEdge[];
  nodes: Record<string, TraceNode>;
}

export interface JobStatus {
  id: string;
  kind: string;
  status: string;
  session_id: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  paused_at?: string | null;
}

export interface CheckpointResponse {
  job_id: string;
  paused_at: "extractor" | "architect" | "generator";
  state: {
    requirements?: Array<Record<string, unknown>>;
    plan?: Record<string, unknown> | null;
    test_cases?: Array<Record<string, unknown>>;
    user_feedback?: Record<string, string[]>;
    [k: string]: unknown;
  };
}

// --- Defect taxonomy --------------------------------------------------------

export type DefectSeverity = "critical" | "major" | "minor";
export type DefectTargetKind = "requirement" | "test_case" | "test_plan";
export type DefectDetector =
  | "static"
  | "reviewer"
  | "requirement_reviewer"
  | "traceability";
export type DefectDetectionDifficulty =
  | "mechanical"
  | "llm"
  | "domain_expert";

// String form keeps us forward-compatible with new enum entries.
export type DefectType = string;

export interface DefectInstance {
  id: string;
  defect_type: DefectType;
  severity: DefectSeverity;
  target_kind: DefectTargetKind;
  target_id: string;
  evidence: string;
  suggestion: string | null;
  // detector is internal-only — server populates it for telemetry but the
  // UI shouldn't surface implementation detail to QA engineers.
  detector?: DefectDetector;
}

export interface DefectReport {
  plan_id: string | null;
  defects: DefectInstance[];
  summary: Partial<Record<DefectSeverity, number>>;
  approved: boolean;
}

export interface DefectCatalogEntry {
  id: DefectType;
  name: string;
  category: "requirement" | "test_plan";
  default_severity: DefectSeverity;
  detection_difficulty: DefectDetectionDifficulty;
  standard_refs: string[];
  description: string;
  example: string | null;
  corrected_example: string | null;
}

export interface DefectCatalogResponse {
  entries: DefectCatalogEntry[];
}
