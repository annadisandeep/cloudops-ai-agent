import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Server } from 'lucide-react'
import { getMetrics, getResource, listResources } from '../api/client'
import type { CloudResource } from '../api/types'
import { useApi, useDebouncedValue } from '../hooks/useApi'
import { useApp } from '../context/AppContext'
import { Card } from '../components/Card'
import { DataTable, Pagination, type Column } from '../components/DataTable'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { MetricChart } from '../components/MetricChart'
import { PageHeader } from '../components/PageHeader'
import { ProviderBadge } from '../components/ProviderBadge'
import { SearchInput } from '../components/SearchInput'
import { Select } from '../components/Select'
import { SimulatedBadge } from '../components/SimulatedBadge'
import { StatusDot } from '../components/StatusBadge'
import { SlideOver } from '../components/SlideOver'
import { formatDateTime } from '../lib/format'

const PAGE_SIZE = 20

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'running', label: 'Running' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'terminated', label: 'Terminated' },
]

function ResourceDetailPanel({ resource }: { resource: CloudResource }) {
  const navigate = useNavigate()
  const detail = useApi(
    () => getResource(resource.provider, resource.id),
    [resource.provider, resource.id],
  )
  const metrics = useApi(
    () =>
      getMetrics({
        provider: resource.provider,
        resource_id: resource.id,
        metric: 'cpu_utilization',
      }),
    [resource.provider, resource.id],
  )

  const full = detail.data ?? resource

  const fields: Array<[string, React.ReactNode]> = [
    ['ID', <span key="id" className="font-mono text-xs">{full.id}</span>],
    ['Provider', <ProviderBadge key="p" provider={full.provider} />],
    ['Account', full.account],
    ['Type', full.type],
    ['Zone / region', full.zone],
    ['Status', <StatusDot key="s" status={full.status} />],
    ['Machine type', <span key="m" className="font-mono text-xs">{full.machine_type}</span>],
    ['Internal IP', <span key="i" className="font-mono text-xs">{full.internal_ip ?? '—'}</span>],
    ['External IP', <span key="e" className="font-mono text-xs">{full.external_ip ?? '—'}</span>],
    ['Created', formatDateTime(full.created_at)],
  ]

  return (
    <div className="space-y-5">
      {full.simulated && <SimulatedBadge />}
      <dl className="space-y-2">
        {fields.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3 text-[13px]">
            <dt className="shrink-0 text-xs text-muted">{label}</dt>
            <dd className="text-right">{value}</dd>
          </div>
        ))}
      </dl>

      {Object.keys(full.labels).length > 0 && (
        <div>
          <p className="mb-1.5 text-xs text-muted">Labels</p>
          <div className="flex flex-wrap gap-1">
            {Object.entries(full.labels).map(([k, v]) => (
              <span
                key={k}
                className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-2xs"
              >
                {k}={v}
              </span>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="mb-1.5 text-xs text-muted">CPU utilization (last hour)</p>
        {metrics.loading ? (
          <LoadingSkeleton rows={3} />
        ) : metrics.error ? (
          <p className="text-xs text-muted">Metrics unavailable: {metrics.error}</p>
        ) : metrics.data ? (
          <MetricChart
            points={metrics.data.points}
            unit={metrics.data.unit}
            height={120}
            ariaLabel={`CPU utilization for ${full.name}`}
          />
        ) : null}
      </div>

      <button
        type="button"
        className="btn-primary w-full justify-center"
        onClick={() =>
          navigate('/investigate', {
            state: {
              resourceId: full.id,
              provider: full.provider,
              scenarioId: full.scenario_ids?.[0] ?? null,
            },
          })
        }
      >
        Investigate this resource
      </button>
    </div>
  )
}

export function ResourcesPage() {
  const { providers, selectedProvider, selectedAccount } = useApp()
  const [query, setQuery] = useState('')
  const [providerFilter, setProviderFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<CloudResource | null>(null)

  const debouncedQuery = useDebouncedValue(query, 250)
  const effectiveProvider = providerFilter || selectedProvider

  const providerOptions = useMemo(
    () => [
      { value: '', label: 'Active provider' },
      ...providers.map((p) => ({
        value: p.id,
        label: p.name,
        disabled: !p.enabled,
      })),
    ],
    [providers],
  )

  const { data, loading, error, retry } = useApi(
    () =>
      listResources({
        provider: effectiveProvider,
        account: providerFilter ? undefined : (selectedAccount ?? undefined),
        q: debouncedQuery || undefined,
        status: statusFilter || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    [effectiveProvider, selectedAccount, providerFilter, debouncedQuery, statusFilter, page],
  )

  const columns: Column<CloudResource>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (r) => (
        <span className="inline-flex items-center gap-2 font-medium">
          {r.name}
          {r.simulated && <SimulatedBadge />}
        </span>
      ),
    },
    {
      key: 'provider',
      header: 'Provider',
      render: (r) => <ProviderBadge provider={r.provider} />,
    },
    { key: 'type', header: 'Type', render: (r) => <span className="text-xs">{r.type}</span> },
    {
      key: 'zone',
      header: 'Zone',
      render: (r) => <span className="text-xs text-muted">{r.zone}</span>,
    },
    { key: 'status', header: 'Status', render: (r) => <StatusDot status={r.status} /> },
    {
      key: 'machine',
      header: 'Machine type',
      render: (r) => <span className="font-mono text-xs">{r.machine_type}</span>,
    },
    {
      key: 'ips',
      header: 'IPs',
      render: (r) => (
        <span className="font-mono text-xs text-muted">
          {[r.internal_ip, r.external_ip].filter(Boolean).join(' / ') || '—'}
        </span>
      ),
    },
    {
      key: 'labels',
      header: 'Labels',
      render: (r) => (
        <span className="flex max-w-[220px] flex-wrap gap-1">
          {Object.entries(r.labels)
            .slice(0, 3)
            .map(([k, v]) => (
              <span
                key={k}
                className="rounded border border-line bg-surface px-1 py-px font-mono text-2xs"
              >
                {k}={v}
              </span>
            ))}
        </span>
      ),
    },
  ]

  return (
    <div>
      <PageHeader title="Resources" description="Inventory across connected providers" />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <SearchInput
          value={query}
          onChange={(v) => {
            setQuery(v)
            setPage(1)
          }}
          placeholder="Search by name or ID…"
          label="Search resources"
          className="w-64"
        />
        <Select
          label="Filter by provider"
          value={providerFilter}
          onChange={(v) => {
            setProviderFilter(v)
            setPage(1)
          }}
          options={providerOptions}
        />
        <Select
          label="Filter by status"
          value={statusFilter}
          onChange={(v) => {
            setStatusFilter(v)
            setPage(1)
          }}
          options={STATUS_OPTIONS}
        />
      </div>

      <Card className="p-0 [&>div]:p-0">
        {loading ? (
          <LoadingSkeleton rows={8} className="p-4" />
        ) : error ? (
          <ErrorState message={error} onRetry={retry} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            icon={Server}
            title="No resources found"
            description="Try adjusting the search or filters."
          />
        ) : (
          <>
            <DataTable
              aria-label="Resources"
              columns={columns}
              rows={data.items}
              rowKey={(r) => `${r.provider}/${r.id}`}
              onRowClick={setSelected}
            />
            <div className="px-3">
              <Pagination
                page={data.page}
                pageSize={data.page_size}
                total={data.total}
                onPageChange={setPage}
              />
            </div>
          </>
        )}
      </Card>

      <SlideOver
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.name ?? ''}
      >
        {selected && <ResourceDetailPanel resource={selected} />}
      </SlideOver>
    </div>
  )
}
