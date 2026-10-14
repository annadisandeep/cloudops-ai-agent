import type {
  AppConfig,
  CloudResource,
  CreateInvestigationRequest,
  HealthResponse,
  Investigation,
  InvestigationSummary,
  LogSeverity,
  LogsResponse,
  MetricSeries,
  OverviewResponse,
  Paginated,
  ProvidersResponse,
  ScenariosResponse,
} from './types'

const API_BASE: string =
  (import.meta.env?.VITE_API_BASE as string | undefined) ?? ''

const API_PREFIX = '/api/v1'

export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

function buildQuery(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value))
    }
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${API_PREFIX}${path}`, {
      headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
      ...init,
    })
  } catch {
    throw new ApiError(
      'network_error',
      'Could not reach the CloudOps Agent API. Is the backend running?',
      0,
    )
  }

  if (!response.ok) {
    let code = 'http_error'
    let message = `Request failed with status ${response.status}`
    try {
      const body: unknown = await response.json()
      if (body && typeof body === 'object') {
        const envelope = body as {
          error?: { code?: string; message?: string }
          detail?: { error?: { code?: string; message?: string } } | string
        }
        const err =
          envelope.error ??
          (typeof envelope.detail === 'object' && envelope.detail !== null
            ? envelope.detail.error
            : undefined)
        if (err) {
          code = err.code ?? code
          message = err.message ?? message
        } else if (typeof envelope.detail === 'string') {
          message = envelope.detail
        }
      }
    } catch {
      // Non-JSON error body — keep defaults.
    }
    throw new ApiError(code, message, response.status)
  }

  return (await response.json()) as T
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// ---- Endpoint wrappers ----

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health')
}

export function getConfig(): Promise<AppConfig> {
  return apiFetch<AppConfig>('/config')
}

export function getProviders(): Promise<ProvidersResponse> {
  return apiFetch<ProvidersResponse>('/providers')
}

export function getScenarios(): Promise<ScenariosResponse> {
  return apiFetch<ScenariosResponse>('/scenarios')
}

export function getOverview(): Promise<OverviewResponse> {
  return apiFetch<OverviewResponse>('/overview')
}

export interface ListResourcesParams {
  provider: string
  account?: string
  q?: string
  type?: string
  status?: string
  page?: number
  page_size?: number
}

export function listResources(
  params: ListResourcesParams,
): Promise<Paginated<CloudResource>> {
  return apiFetch<Paginated<CloudResource>>(`/resources${buildQuery(params)}`)
}

export function getResource(
  provider: string,
  resourceId: string,
): Promise<CloudResource> {
  return apiFetch<CloudResource>(
    `/resources/${encodeURIComponent(provider)}/${encodeURIComponent(resourceId)}`,
  )
}

export interface GetMetricsParams {
  provider: string
  resource_id: string
  metric: string
  start?: string
  end?: string
  step_seconds?: number
}

export function getMetrics(params: GetMetricsParams): Promise<MetricSeries> {
  return apiFetch<MetricSeries>(`/metrics${buildQuery(params)}`)
}

export interface GetLogsParams {
  provider: string
  resource_id: string
  start?: string
  end?: string
  severity?: LogSeverity
  q?: string
  limit?: number
}

export function getLogs(params: GetLogsParams): Promise<LogsResponse> {
  return apiFetch<LogsResponse>(`/logs${buildQuery(params)}`)
}

export function createInvestigation(
  body: CreateInvestigationRequest,
): Promise<Investigation> {
  return apiPost<Investigation>('/investigations', body)
}

export interface ListInvestigationsParams {
  q?: string
  provider?: string
  status?: string
  page?: number
  page_size?: number
}

export function listInvestigations(
  params: ListInvestigationsParams = {},
): Promise<Paginated<InvestigationSummary>> {
  return apiFetch<Paginated<InvestigationSummary>>(
    `/investigations${buildQuery(params)}`,
  )
}

export function getInvestigation(id: string): Promise<Investigation> {
  return apiFetch<Investigation>(`/investigations/${encodeURIComponent(id)}`)
}

export function investigationReportUrl(id: string): string {
  return `${API_BASE}${API_PREFIX}/investigations/${encodeURIComponent(id)}/report.md`
}

export async function downloadReportMarkdown(id: string): Promise<string> {
  let response: Response
  try {
    response = await fetch(investigationReportUrl(id), {
      headers: { Accept: 'text/markdown' },
    })
  } catch {
    throw new ApiError(
      'network_error',
      'Could not reach the CloudOps Agent API.',
      0,
    )
  }
  if (!response.ok) {
    throw new ApiError(
      'report_unavailable',
      `Report download failed with status ${response.status}`,
      response.status,
    )
  }
  return response.text()
}
