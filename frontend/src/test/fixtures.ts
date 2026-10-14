import type {
  AppConfig,
  CloudResource,
  Investigation,
  InvestigationSummary,
  Paginated,
  Provider,
} from '../api/types'

export const fixtureConfig: AppConfig = {
  demo_mode: true,
  providers: {
    demo: { enabled: true, mode: 'demo' },
    gcp: { enabled: false, mode: 'read-only', allowed_projects: [] },
    aws: { enabled: false, mode: 'read-only', allowed_accounts: [] },
  },
  llm: { provider: 'mock', model: 'deterministic-v1' },
  limits: {
    max_steps: 8,
    tool_timeout_seconds: 20,
    investigation_timeout_seconds: 120,
  },
}

export const fixtureProviders: Provider[] = [
  {
    id: 'demo',
    name: 'Demo Environment',
    enabled: true,
    mode: 'demo',
    accounts: [{ id: 'demo-project', name: 'Demo Project', kind: 'project' }],
  },
  {
    id: 'gcp',
    name: 'Google Cloud Platform',
    enabled: false,
    mode: 'read-only',
    accounts: [],
  },
  {
    id: 'aws',
    name: 'Amazon Web Services',
    enabled: false,
    mode: 'read-only',
    accounts: [],
  },
]

export const fixtureResources: Paginated<CloudResource> = {
  items: [
    {
      id: 'web-frontend-1',
      provider: 'gcp',
      account: 'demo-project',
      name: 'web-frontend-1',
      type: 'compute-instance',
      zone: 'us-central1-a',
      status: 'running',
      machine_type: 'e2-standard-2',
      internal_ip: '10.0.0.11',
      external_ip: null,
      labels: { env: 'prod', service: 'web' },
      created_at: '2026-01-10T08:00:00Z',
      simulated: true,
    },
    {
      id: 'db-primary-1',
      provider: 'aws',
      account: 'demo-project',
      name: 'db-primary-1',
      type: 'ec2-instance',
      zone: 'us-east-1a',
      status: 'stopped',
      machine_type: 'm5.large',
      internal_ip: '10.0.1.5',
      external_ip: '54.1.2.3',
      labels: { env: 'prod' },
      created_at: '2026-01-11T08:00:00Z',
      simulated: true,
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
}

export const fixtureCompletedInvestigation: Investigation = {
  id: 'inv_8f3a2c',
  question: 'Why is my GCP VM experiencing high CPU utilization?',
  provider: 'demo',
  resource_id: 'web-frontend-1',
  scenario_id: 'gcp-high-cpu',
  status: 'completed',
  created_at: '2026-02-01T14:00:00Z',
  completed_at: '2026-02-01T14:00:08Z',
  time_window: { start: '2026-02-01T13:00:00Z', end: '2026-02-01T14:00:00Z' },
  steps: [
    {
      index: 0,
      tool: 'get_metrics',
      status: 'completed',
      input: { resource_id: 'web-frontend-1', metric: 'cpu_utilization' },
      output_summary: '60 points; min 12.1%, max 96.8%, last 94.2%',
      started_at: '2026-02-01T14:00:01Z',
      duration_ms: 12,
      evidence_ids: ['ev_1'],
      error: null,
    },
    {
      index: 1,
      tool: 'get_logs',
      status: 'completed',
      input: { resource_id: 'web-frontend-1', severity: 'ERROR' },
      output_summary: '3 ERROR entries in window',
      started_at: '2026-02-01T14:00:02Z',
      duration_ms: 9,
      evidence_ids: ['ev_2'],
      error: null,
    },
  ],
  evidence: [
    {
      id: 'ev_1',
      type: 'metric',
      source_tool: 'get_metrics',
      title: 'cpu_utilization for web-frontend-1',
      summary: 'CPU sustained above 90% from 14:05 to 14:40 UTC',
      data: { points: 60 },
      simulated: true,
    },
    {
      id: 'ev_2',
      type: 'log',
      source_tool: 'get_logs',
      title: 'ERROR logs for web-frontend-1',
      summary: 'Repeated worker saturation errors',
      data: {
        entries: [
          {
            timestamp: '2026-02-01T13:40:00Z',
            severity: 'ERROR',
            message: 'worker pool saturated',
          },
        ],
      },
      simulated: true,
    },
  ],
  report: {
    summary:
      'CPU utilization on web-frontend-1 was sustained above 90% due to worker pool saturation.',
    severity_assessment: 'high',
    observed_facts: [
      {
        statement: 'CPU exceeded 90% for 35 minutes',
        evidence_ids: ['ev_1'],
      },
    ],
    possible_causes: [
      {
        cause: 'Traffic spike exceeding instance capacity',
        likelihood: 'likely',
        rationale: 'Request count rose in lockstep with CPU.',
        evidence_ids: ['ev_1', 'ev_2'],
      },
    ],
    recommendations: [
      {
        action: 'Scale the instance group horizontally',
        risk: 'low',
        rationale: 'Adds headroom without downtime.',
      },
    ],
    confidence: 'high',
    limitations: ['Demo data only — live traffic sources were not inspected.'],
    llm_provider: 'mock',
  },
  error: null,
  simulated: true,
}

export const fixtureEmptyInvestigations: Paginated<InvestigationSummary> = {
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
}
