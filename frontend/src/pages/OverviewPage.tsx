import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, CheckCircle2, Inbox } from 'lucide-react'
import { getOverview } from '../api/client'
import { useApi } from '../hooks/useApi'
import { Card } from '../components/Card'
import { DataTable, type Column } from '../components/DataTable'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { PageHeader } from '../components/PageHeader'
import { ProviderBadge } from '../components/ProviderBadge'
import { SimulatedBadge } from '../components/SimulatedBadge'
import { StatusBadge, StatusDot } from '../components/StatusBadge'
import { formatDateTime } from '../lib/format'
import type { InvestigationSummary } from '../api/types'

function StatCard({ label, value, detail }: { label: string; value: number | string; detail?: string }) {
  return (
    <div className="rounded-md border border-line bg-bg px-4 py-3">
      <p className="text-2xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tnum">{value}</p>
      {detail && <p className="mt-0.5 text-2xs text-muted">{detail}</p>}
    </div>
  )
}

const investigationColumns: Column<InvestigationSummary>[] = [
  {
    key: 'question',
    header: 'Question',
    render: (inv) => (
      <Link
        to={`/investigations/${inv.id}`}
        className="font-medium hover:underline"
        onClick={(e) => e.stopPropagation()}
      >
        {inv.question}
      </Link>
    ),
  },
  {
    key: 'resource',
    header: 'Resource',
    render: (inv) => <span className="font-mono text-xs">{inv.resource_id ?? '—'}</span>,
  },
  {
    key: 'status',
    header: 'Status',
    render: (inv) => <StatusBadge status={inv.status} />,
  },
  {
    key: 'severity',
    header: 'Severity',
    render: (inv) =>
      inv.severity_assessment ? <StatusBadge status={inv.severity_assessment} /> : <span className="text-muted">—</span>,
  },
  {
    key: 'created',
    header: 'Created',
    render: (inv) => <span className="text-xs text-muted tnum">{formatDateTime(inv.created_at)}</span>,
  },
]

export function OverviewPage() {
  const navigate = useNavigate()
  const { data, loading, error, retry } = useApi(() => getOverview(), [])

  if (loading) return <LoadingSkeleton rows={8} />
  if (error) return <ErrorState message={error} onRetry={retry} />
  if (!data) return null

  const { resource_counts: counts, attention, recent_investigations } = data
  const byProvider = Object.entries(counts.by_provider)
    .map(([p, n]) => `${p.toUpperCase()} ${n}`)
    .join(' · ')

  return (
    <div>
      <PageHeader
        title="Overview"
        description="Environment health at a glance"
        actions={data.simulated ? <SimulatedBadge /> : undefined}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Total resources" value={counts.total} detail={byProvider || undefined} />
        <StatCard
          label="Running"
          value={counts.by_status['running'] ?? 0}
          detail={Object.entries(counts.by_status)
            .filter(([s]) => s !== 'running')
            .map(([s, n]) => `${s} ${n}`)
            .join(' · ') || undefined}
        />
        <StatCard label="Needs attention" value={attention.length} />
        <StatCard label="Investigations run" value={recent_investigations.length} detail="recent" />
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        <Card title="Needs attention">
          {attention.length === 0 ? (
            <EmptyState
              icon={CheckCircle2}
              title="All clear"
              description="No resources currently need attention."
            />
          ) : (
            <ul className="divide-y divide-line">
              {attention.map((item) => (
                <li
                  key={`${item.provider}-${item.resource_id}-${item.reason}`}
                  className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0"
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <StatusDot status={item.severity} label="" />
                    <div className="min-w-0">
                      <p className="truncate font-mono text-xs font-medium">{item.resource_id}</p>
                      <p className="truncate text-xs text-muted">{item.reason}</p>
                    </div>
                    <ProviderBadge provider={item.provider} />
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      navigate('/investigate', {
                        state: {
                          scenarioId: item.scenario_id,
                          resourceId: item.resource_id,
                          provider: item.provider,
                        },
                      })
                    }
                    className="inline-flex shrink-0 items-center gap-1 text-xs font-medium hover:underline"
                  >
                    Investigate
                    <ArrowRight size={12} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Recent investigations"
          actions={
            <Link to="/history" className="text-xs text-muted hover:text-fg hover:underline">
              View all
            </Link>
          }
        >
          {recent_investigations.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title="No investigations yet"
              description="Run your first investigation from the Investigate page."
              action={
                <Link to="/investigate" className="btn-primary">
                  New investigation
                </Link>
              }
            />
          ) : (
            <DataTable
              aria-label="Recent investigations"
              columns={investigationColumns}
              rows={recent_investigations.slice(0, 5)}
              rowKey={(inv) => inv.id}
              onRowClick={(inv) => navigate(`/investigations/${inv.id}`)}
            />
          )}
        </Card>
      </div>

    </div>
  )
}
