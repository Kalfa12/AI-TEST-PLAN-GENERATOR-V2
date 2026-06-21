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

export type ProviderName = "groq" | "gemini" | "mistral" | "deepseek";

export interface ProviderKey {
  id: string;
  provider: ProviderName;
  label: string;
  key_tail: string;
  is_enabled: boolean;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ProviderKeyCreated extends ProviderKey {
  api_key: string;
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
  steps?: TestStep[];
  acceptance_criteria?: AcceptanceCriterion[];
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
}

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
