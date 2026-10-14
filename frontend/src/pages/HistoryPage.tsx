import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clock } from 'lucide-react'
import { listInvestigations } from '../api/client'
import type { InvestigationSummary } from '../api/types'
import { useApi, useDebouncedValue } from '../hooks/useApi'
import { useApp } from '../context/AppContext'
import { Card } from '../components/Card'
import { DataTable, Pagination, type Column } from '../components/DataTable'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { PageHeader } from '../components/PageHeader'
import { ProviderBadge } from '../components/ProviderBadge'
import { SearchInput } from '../components/SearchInput'
import { Select } from '../components/Select'
import { StatusBadge } from '../components/StatusBadge'
import { durationBetween, formatDateTime } from '../lib/format'

const PAGE_SIZE = 20

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'queued', label: 'Queued' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

export function HistoryPage() {
  const navigate = useNavigate()
  const { providers } = useApp()
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [providerFilter, setProviderFilter] = useState('')
  const [page, setPage] = useState(1)

  const debouncedQuery = useDebouncedValue(query, 250)

  const { data, loading, error, retry } = useApi(
    () =>
      listInvestigations({
        q: debouncedQuery || undefined,
        status: statusFilter || undefined,
        provider: providerFilter || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    [debouncedQuery, statusFilter, providerFilter, page],
  )

  const columns: Column<InvestigationSummary>[] = [
    {
      key: 'question',
      header: 'Question',
      render: (inv) => <span className="font-medium">{inv.question}</span>,
      className: 'max-w-[360px]',
    },
    {
      key: 'resource',
      header: 'Resource',
      render: (inv) => <span className="font-mono text-xs">{inv.resource_id ?? '—'}</span>,
    },
    {
      key: 'provider',
      header: 'Provider',
      render: (inv) => <ProviderBadge provider={inv.provider} />,
    },
    { key: 'status', header: 'Status', render: (inv) => <StatusBadge status={inv.status} /> },
    {
      key: 'severity',
      header: 'Severity',
      render: (inv) =>
        inv.severity_assessment ? (
          <StatusBadge status={inv.severity_assessment} />
        ) : (
          <span className="text-muted">—</span>
        ),
    },
    {
      key: 'created',
      header: 'Created',
      render: (inv) => (
        <span className="text-xs text-muted tnum">{formatDateTime(inv.created_at)}</span>
      ),
    },
    {
      key: 'duration',
      header: 'Duration',
      render: (inv) => (
        <span className="text-xs text-muted tnum">
          {durationBetween(inv.created_at, inv.completed_at)}
        </span>
      ),
    },
  ]

  const hasFilters = Boolean(debouncedQuery || statusFilter || providerFilter)

  return (
    <div>
      <PageHeader title="History" description="All investigations run by the agent" />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <SearchInput
          value={query}
          onChange={(v) => {
            setQuery(v)
            setPage(1)
          }}
          placeholder="Search question or resource…"
          label="Search investigations"
          className="w-64"
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
        <Select
          label="Filter by provider"
          value={providerFilter}
          onChange={(v) => {
            setProviderFilter(v)
            setPage(1)
          }}
          options={[
            { value: '', label: 'All providers' },
            ...providers.map((p) => ({ value: p.id, label: p.name })),
          ]}
        />
      </div>

      <Card className="p-0 [&>div]:p-0">
        {loading ? (
          <LoadingSkeleton rows={8} className="p-4" />
        ) : error ? (
          <ErrorState message={error} onRetry={retry} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            icon={Clock}
            title={hasFilters ? 'No matching investigations' : 'No investigations yet'}
            description={
              hasFilters
                ? 'Try different search terms or filters.'
                : 'Start your first investigation to see it here.'
            }
            action={
              !hasFilters ? (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => navigate('/investigate')}
                >
                  New investigation
                </button>
              ) : undefined
            }
          />
        ) : (
          <>
            <DataTable
              aria-label="Investigations"
              columns={columns}
              rows={data.items}
              rowKey={(inv) => inv.id}
              onRowClick={(inv) => navigate(`/investigations/${inv.id}`)}
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
    </div>
  )
}
