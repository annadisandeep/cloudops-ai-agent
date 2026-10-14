// API types — match docs/API.md (v1) exactly.

export type ProviderId = 'demo' | 'gcp' | 'aws'

export type Severity = 'critical' | 'high' | 'medium' | 'low'

export type ScenarioCategory =
  | 'performance'
  | 'memory'
  | 'errors'
  | 'deployment'
  | 'storage'

export interface TimeWindow {
  start: string
  end: string
}

// GET /api/v1/health
export interface HealthResponse {
  status: string
  version: string
  time: string
}

// GET /api/v1/config
export interface ProviderConfigEntry {
  enabled: boolean
  mode: string
  allowed_projects?: string[]
  allowed_accounts?: string[]
}

export interface AppConfig {
  demo_mode: boolean
  providers: Record<string, ProviderConfigEntry>
  llm: {
    provider: 'mock' | 'gemini'
    model: string
  }
  limits: {
    max_steps: number
    tool_timeout_seconds: number
    investigation_timeout_seconds: number
  }
}

// GET /api/v1/providers
export interface ProviderAccount {
  id: string
  name: string
  kind: string
}

export interface Provider {
  id: ProviderId
  name: string
  enabled: boolean
  mode: string
  accounts: ProviderAccount[]
}

export interface ProvidersResponse {
  items: Provider[]
}

// GET /api/v1/scenarios
export interface Scenario {
  id: string
  title: string
  provider: string
  severity: Severity
  category: ScenarioCategory
  resource_id: string
  resource_name: string
  description: string
  time_window: TimeWindow
  suggested_question: string
  simulated: boolean
}

export interface ScenariosResponse {
  items: Scenario[]
}

// GET /api/v1/overview
export interface AttentionItem {
  resource_id: string
  provider: string
  reason: string
  severity: Severity
  scenario_id: string | null
}

export interface OverviewResponse {
  resource_counts: {
    total: number
    by_provider: Record<string, number>
    by_status: Record<string, number>
  }
  attention: AttentionItem[]
  recent_investigations: InvestigationSummary[]
  simulated?: boolean
}

// GET /api/v1/resources
export interface CloudResource {
  id: string
  provider: string
  account: string
  name: string
  type: string
  zone: string
  status: string
  machine_type: string
  internal_ip: string | null
  external_ip: string | null
  labels: Record<string, string>
  created_at: string
  simulated?: boolean
  scenario_ids?: string[]
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// GET /api/v1/metrics
export type MetricName =
  | 'cpu_utilization'
  | 'memory_available_mb'
  | 'disk_used_percent'
  | 'network_in_bytes'
  | 'network_out_bytes'
  | 'http_5xx_count'
  | 'http_request_count'
  | 'latency_ms_p95'

export interface MetricPoint {
  timestamp: string
  value: number
}

export interface MetricSeries {
  provider: string
  resource_id: string
  metric: string
  unit: string
  points: MetricPoint[]
  simulated?: boolean
}

// GET /api/v1/logs
export type LogSeverity = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

export interface LogEntry {
  timestamp: string
  severity: LogSeverity
  message: string
  source: string
}

export interface LogsResponse {
  entries: LogEntry[]
  total: number
  simulated?: boolean
}

// Investigations
export type InvestigationStatus = 'queued' | 'running' | 'completed' | 'failed'
export type StepStatus = 'running' | 'completed' | 'failed'
export type Likelihood = 'likely' | 'possible' | 'unlikely'
export type Risk = 'low' | 'medium' | 'high'
export type Confidence = 'high' | 'medium' | 'low'

export interface CreateInvestigationRequest {
  question: string
  provider: string
  scenario_id?: string
  resource_id?: string
  time_window?: TimeWindow
}

export interface InvestigationStep {
  index: number
  tool: string
  status: StepStatus
  input: Record<string, unknown>
  output_summary: string | null
  started_at: string
  duration_ms: number | null
  evidence_ids: string[]
  error: string | null
}

export type EvidenceType = 'metric' | 'log' | 'metadata'

export interface Evidence {
  id: string
  type: EvidenceType
  source_tool: string
  title: string
  summary: string
  data: unknown
  simulated?: boolean
}

export interface ObservedFact {
  statement: string
  evidence_ids: string[]
}

export interface PossibleCause {
  cause: string
  likelihood: Likelihood
  rationale: string
  evidence_ids: string[]
}

export interface Recommendation {
  action: string
  risk: Risk
  rationale: string
}

export interface Report {
  summary: string
  severity_assessment: Severity
  observed_facts: ObservedFact[]
  possible_causes: PossibleCause[]
  recommendations: Recommendation[]
  confidence: Confidence
  limitations: string[]
  llm_provider: string
}

export interface InvestigationSummary {
  id: string
  question: string
  provider: string
  resource_id: string | null
  scenario_id: string | null
  status: InvestigationStatus
  severity_assessment: Severity | null
  created_at: string
  completed_at: string | null
  step_count: number
  simulated?: boolean
}

export interface Investigation {
  id: string
  question: string
  provider: string
  resource_id: string | null
  scenario_id: string | null
  status: InvestigationStatus
  created_at: string
  completed_at: string | null
  time_window: TimeWindow | null
  steps: InvestigationStep[]
  evidence: Evidence[]
  report: Report | null
  error: string | null
  simulated?: boolean
}

// Error envelope
export interface ApiErrorEnvelope {
  error: {
    code: string
    message: string
  }
}
