import { useMemo, useState } from 'react'
import { Activity } from 'lucide-react'
import { getMetrics, listResources } from '../api/client'
import type { MetricName } from '../api/types'
import { useApi } from '../hooks/useApi'
import { useApp } from '../context/AppContext'
import { Card } from '../components/Card'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { MetricChart } from '../components/MetricChart'
import { PageHeader } from '../components/PageHeader'
import { Select } from '../components/Select'
import { SimulatedBadge } from '../components/SimulatedBadge'

const METRIC_CARDS: Array<{ metric: MetricName; title: string; threshold?: number }> = [
  { metric: 'cpu_utilization', title: 'CPU utilization', threshold: 90 },
  { metric: 'memory_available_mb', title: 'Memory available (MB)' },
  { metric: 'http_5xx_count', title: 'HTTP 5xx count' },
  { metric: 'latency_ms_p95', title: 'Latency p95 (ms)' },
]

const EXTRA_METRICS: Array<{ value: MetricName; label: string }> = [
  { value: 'cpu_utilization', label: 'CPU utilization' },
  { value: 'memory_available_mb', label: 'Memory available (MB)' },
  { value: 'disk_used_percent', label: 'Disk used (%)' },
  { value: 'network_in_bytes', label: 'Network in (bytes)' },
  { value: 'network_out_bytes', label: 'Network out (bytes)' },
  { value: 'http_5xx_count', label: 'HTTP 5xx count' },
  { value: 'http_request_count', label: 'HTTP request count' },
  { value: 'latency_ms_p95', label: 'Latency p95 (ms)' },
]

const RANGES = [
  { value: '1', label: 'Last 1 hour' },
  { value: '6', label: 'Last 6 hours' },
  { value: '24', label: 'Last 24 hours' },
]

function rangeToWindow(hours: number): { start: string; end: string; step: number } {
  const end = new Date()
  const start = new Date(end.getTime() - hours * 3600 * 1000)
  return {
    start: start.toISOString(),
    end: end.toISOString(),
    step: hours <= 1 ? 60 : hours <= 6 ? 300 : 900,
  }
}

function MetricCard({
  provider,
  resourceId,
  metric,
  title,
  threshold,
  hours,
}: {
  provider: string
  resourceId: string
  metric: MetricName
  title: string
  threshold?: number
  hours: number
}) {
  const { data, loading, error, retry } = useApi(() => {
    const { start, end, step } = rangeToWindow(hours)
    return getMetrics({
      provider,
      resource_id: resourceId,
      metric,
      start,
      end,
      step_seconds: step,
    })
  }, [provider, resourceId, metric, hours])

  return (
    <Card
      title={title}
      actions={data?.simulated ? <SimulatedBadge /> : undefined}
    >
      {loading ? (
        <LoadingSkeleton rows={4} />
      ) : error ? (
        <ErrorState message={error} onRetry={retry} />
      ) : data ? (
        <MetricChart
          points={data.points}
          unit={data.unit}
          threshold={threshold}
          ariaLabel={`${title} for ${resourceId}`}
        />
      ) : null}
    </Card>
  )
}

export function MonitoringPage() {
  const { selectedProvider, selectedAccount } = useApp()
  const [resourceId, setResourceId] = useState('')
  const [extraMetric, setExtraMetric] = useState<MetricName>('disk_used_percent')
  const [range, setRange] = useState('1')

  const resources = useApi(
    () =>
      listResources({
        provider: selectedProvider,
        account: selectedAccount ?? undefined,
        page_size: 100,
      }),
    [selectedProvider, selectedAccount],
  )

  const resourceOptions = useMemo(() => {
    const items = resources.data?.items ?? []
    return items.map((r) => ({ value: r.id, label: r.name }))
  }, [resources.data])

  const activeResource =
    resourceId || (resourceOptions.length > 0 ? resourceOptions[0].value : '')
  const hours = Number(range)

  return (
    <div>
      <PageHeader title="Monitoring" description="Metrics for the selected resource" />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {resources.loading ? (
          <LoadingSkeleton rows={1} className="w-56" />
        ) : (
          <Select
            label="Resource"
            value={activeResource}
            onChange={setResourceId}
            options={
              resourceOptions.length > 0
                ? resourceOptions
                : [{ value: '', label: 'No resources available', disabled: true }]
            }
            className="min-w-[200px]"
          />
        )}
        <Select
          label="Additional metric"
          value={extraMetric}
          onChange={(v) => setExtraMetric(v as MetricName)}
          options={EXTRA_METRICS}
        />
        <Select label="Time range" value={range} onChange={setRange} options={RANGES} />
      </div>

      {resources.error ? (
        <ErrorState message={resources.error} onRetry={resources.retry} />
      ) : !resources.loading && !activeResource ? (
        <EmptyState
          icon={Activity}
          title="No resources to monitor"
          description="No resources were found for the selected provider."
        />
      ) : activeResource ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {METRIC_CARDS.map((card) => (
            <MetricCard
              key={card.metric}
              provider={selectedProvider}
              resourceId={activeResource}
              metric={card.metric}
              title={card.title}
              threshold={card.threshold}
              hours={hours}
            />
          ))}
          <MetricCard
            provider={selectedProvider}
            resourceId={activeResource}
            metric={extraMetric}
            title={EXTRA_METRICS.find((m) => m.value === extraMetric)?.label ?? extraMetric}
            hours={hours}
          />
        </div>
      ) : null}
    </div>
  )
}
