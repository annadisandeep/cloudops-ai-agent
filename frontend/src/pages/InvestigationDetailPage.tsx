import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  Check,
  Copy,
  Download,
  FileText,
  Info,
  X,
} from 'lucide-react'
import { downloadReportMarkdown, getInvestigation } from '../api/client'
import type { Evidence, Investigation, InvestigationStep, Report } from '../api/types'
import { ErrorState } from '../components/ErrorState'
import { JsonBlock } from '../components/JsonBlock'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { ProviderBadge } from '../components/ProviderBadge'
import { SimulatedBadge } from '../components/SimulatedBadge'
import { Spinner } from '../components/Spinner'
import { StatusBadge } from '../components/StatusBadge'
import {
  durationBetween,
  formatDateTime,
  formatDurationMs,
  formatTimeUtc,
  triggerDownload,
} from '../lib/format'

const EVIDENCE_ICONS = {
  metric: Activity,
  log: FileText,
  metadata: Info,
} as const

function EvidenceChip({ evidenceId }: { evidenceId: string }) {
  return (
    <button
      type="button"
      onClick={() => {
        document
          .getElementById(`evidence-${evidenceId}`)
          ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }}
      className="rounded border border-line bg-surface px-1.5 py-px font-mono text-2xs text-muted transition-colors duration-150 hover:text-fg"
      aria-label={`Jump to evidence ${evidenceId}`}
    >
      {evidenceId}
    </button>
  )
}

function StepIcon({ status }: { status: InvestigationStep['status'] }) {
  if (status === 'running') return <Spinner size={13} label="Step running" />
  if (status === 'failed')
    return <X size={13} aria-label="Step failed" className="text-crit" />
  return <Check size={13} aria-label="Step completed" className="text-ok" />
}

function StepRow({ step }: { step: InvestigationStep }) {
  return (
    <li className="relative pb-5 pl-7 last:pb-0" data-testid="step-row">
      <span className="absolute left-0 top-0.5 flex h-5 w-5 items-center justify-center rounded-full border border-line bg-bg">
        <StepIcon status={step.status} />
      </span>
      <span className="absolute bottom-0 left-2.5 top-6 w-px bg-line [li:last-child_&]:hidden" aria-hidden="true" />
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[13px] font-medium">{step.tool}</span>
        <span className="font-mono text-2xs text-muted tnum">
          {formatDurationMs(step.duration_ms)}
        </span>
        {step.evidence_ids.map((id) => (
          <EvidenceChip key={id} evidenceId={id} />
        ))}
      </div>
      {step.output_summary && (
        <p className="mt-1 text-xs text-muted">{step.output_summary}</p>
      )}
      {step.error && (
        <p className="mt-1 text-xs text-crit" role="alert">
          {step.error}
        </p>
      )}
      <div className="mt-1.5 max-w-xl">
        <JsonBlock data={step.input} label="Input" />
      </div>
    </li>
  )
}

function EvidenceCard({ evidence }: { evidence: Evidence }) {
  const Icon = EVIDENCE_ICONS[evidence.type] ?? Info
  const isLogData =
    evidence.type === 'log' &&
    typeof evidence.data === 'object' &&
    evidence.data !== null &&
    Array.isArray((evidence.data as { entries?: unknown }).entries)

  return (
    <article
      id={`evidence-${evidence.id}`}
      data-testid="evidence-card"
      className="scroll-mt-20 rounded-md border border-line bg-bg p-3"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Icon size={14} aria-hidden="true" className="shrink-0 text-muted" />
          <h3 className="truncate text-[13px] font-medium">{evidence.title}</h3>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="rounded border border-line px-1.5 py-px font-mono text-2xs text-muted">
            {evidence.id}
          </span>
          {evidence.simulated && <SimulatedBadge />}
        </div>
      </div>
      <p className="mt-1.5 text-xs text-muted">{evidence.summary}</p>
      <p className="mt-1 font-mono text-2xs text-muted">via {evidence.source_tool}</p>
      <div className="mt-2">
        {isLogData ? (
          <JsonBlock
            label="Log entries"
            data={(
              (evidence.data as { entries: Array<{ timestamp?: string; severity?: string; message?: string }> })
                .entries
            )
              .map((e) => `${e.timestamp ?? ''} ${e.severity ?? ''} ${e.message ?? ''}`.trim())
              .join('\n')}
          />
        ) : (
          <JsonBlock label="Raw data" data={evidence.data} />
        )}
      </div>
    </article>
  )
}

function ScaleBadge({ value }: { value: string }) {
  return <StatusBadge status={value} />
}

function ReportSection({
  report,
  investigationId,
}: {
  report: Report
  investigationId: string
}) {
  const [copied, setCopied] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const handleExport = async () => {
    setExportError(null)
    try {
      const markdown = await downloadReportMarkdown(investigationId)
      triggerDownload(`${investigationId}-report.md`, markdown)
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setExportError('Could not copy to clipboard')
    }
  }

  return (
    <section
      data-testid="report-section"
      className="rounded-md border border-line bg-bg"
      aria-label="Investigation report"
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="flex items-center gap-2.5">
          <h2 className="text-sm font-semibold">Report</h2>
          <StatusBadge status={report.severity_assessment} />
          <span className="text-2xs text-muted">
            Confidence: <span className="font-medium text-fg">{report.confidence}</span>
          </span>
          <span className="font-mono text-2xs text-muted">llm: {report.llm_provider}</span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={handleExport} className="btn-secondary">
            <Download size={13} aria-hidden="true" />
            Export Markdown
          </button>
          <button type="button" onClick={handleCopyLink} className="btn-secondary">
            <Copy size={13} aria-hidden="true" />
            {copied ? 'Copied' : 'Copy link'}
          </button>
        </div>
      </header>

      <div className="space-y-5 px-4 py-4">
        {exportError && (
          <p role="alert" className="text-xs text-crit">
            {exportError}
          </p>
        )}
        <p className="max-w-3xl text-[13px] leading-6">{report.summary}</p>

        <div>
          <h3 className="mb-2 text-2xs font-medium uppercase tracking-wide text-muted">
            Observed facts
          </h3>
          <ul className="space-y-1.5">
            {report.observed_facts.map((fact, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 text-[13px]">
                <span>{fact.statement}</span>
                {fact.evidence_ids.map((id) => (
                  <EvidenceChip key={id} evidenceId={id} />
                ))}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="mb-2 text-2xs font-medium uppercase tracking-wide text-muted">
            Possible causes
          </h3>
          <ul className="space-y-2.5">
            {report.possible_causes.map((cause, i) => (
              <li key={i} className="rounded border border-line p-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13px] font-medium">{cause.cause}</span>
                  <ScaleBadge value={cause.likelihood} />
                  {cause.evidence_ids.map((id) => (
                    <EvidenceChip key={id} evidenceId={id} />
                  ))}
                </div>
                <p className="mt-1 text-xs text-muted">{cause.rationale}</p>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="mb-2 text-2xs font-medium uppercase tracking-wide text-muted">
            Recommendations
          </h3>
          <ul className="space-y-2.5">
            {report.recommendations.map((rec, i) => (
              <li key={i} className="rounded border border-line p-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13px] font-medium">{rec.action}</span>
                  <span className="rounded border border-line px-1.5 py-px text-2xs text-muted">
                    risk: {rec.risk}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted">{rec.rationale}</p>
              </li>
            ))}
          </ul>
        </div>

        {report.limitations.length > 0 && (
          <div>
            <h3 className="mb-2 text-2xs font-medium uppercase tracking-wide text-muted">
              Limitations
            </h3>
            <ul className="list-disc space-y-1 pl-5 text-xs text-muted">
              {report.limitations.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  )
}

export function InvestigationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [investigation, setInvestigation] = useState<Investigation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const retry = useCallback(() => {
    setError(null)
    setAttempt((a) => a + 1)
  }, [])

  useEffect(() => {
    if (!id) return
    let cancelled = false
    let timer: number | undefined

    const load = async () => {
      try {
        const data = await getInvestigation(id)
        if (cancelled) return
        setInvestigation(data)
        setError(null)
        if (data.status === 'queued' || data.status === 'running') {
          timer = window.setTimeout(load, 1000)
        }
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Failed to load investigation')
      }
    }

    void load()
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [id, attempt])

  if (error && !investigation) return <ErrorState message={error} onRetry={retry} />
  if (!investigation) return <LoadingSkeleton rows={10} />

  const inv = investigation
  const isActive = inv.status === 'queued' || inv.status === 'running'

  return (
    <div>
      <nav aria-label="Breadcrumb" className="mb-3 text-xs text-muted">
        <Link to="/history" className="hover:underline">
          History
        </Link>{' '}
        / <span className="font-mono">{inv.id}</span>
      </nav>

      <header className="mb-5 rounded-md border border-line bg-bg px-4 py-3.5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-base font-semibold leading-6">{inv.question}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
              <StatusBadge status={inv.status} showSpinner />
              <ProviderBadge provider={inv.provider} />
              {inv.resource_id && (
                <span className="font-mono text-xs">{inv.resource_id}</span>
              )}
              {inv.time_window && (
                <span className="tnum">
                  {formatTimeUtc(inv.time_window.start)} – {formatTimeUtc(inv.time_window.end)}
                </span>
              )}
              <span className="tnum">created {formatDateTime(inv.created_at)}</span>
              {inv.completed_at && (
                <span className="tnum">
                  duration {durationBetween(inv.created_at, inv.completed_at)}
                </span>
              )}
              {inv.simulated && <SimulatedBadge />}
            </div>
          </div>
        </div>
      </header>

      {inv.status === 'failed' && (
        <div
          role="alert"
          className="mb-5 flex items-start gap-2.5 rounded-md border border-line border-l-2 border-l-crit bg-bg px-4 py-3"
        >
          <AlertTriangle size={15} aria-hidden="true" className="mt-0.5 shrink-0 text-crit" />
          <div>
            <p className="text-[13px] font-medium">Investigation failed</p>
            <p className="mt-0.5 text-xs text-muted">
              {inv.error ?? 'The agent could not complete this investigation.'}
            </p>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="mb-4 text-xs text-warn">
          Polling error: {error} — retrying may help.{' '}
          <button type="button" onClick={retry} className="underline">
            Retry now
          </button>
        </p>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <section aria-label="Tool execution timeline" className="rounded-md border border-line bg-bg p-4">
          <h2 className="mb-4 text-[13px] font-semibold">
            Tool execution
            {isActive && (
              <span className="ml-2 inline-flex items-center gap-1.5 text-2xs font-normal text-muted">
                <Spinner size={11} label="Investigation in progress" />
                agent working…
              </span>
            )}
          </h2>
          {inv.steps.length === 0 ? (
            <p className="text-xs text-muted">No tool calls yet.</p>
          ) : (
            <ol className="list-none">
              {inv.steps.map((step) => (
                <StepRow key={step.index} step={step} />
              ))}
            </ol>
          )}
        </section>

        <section aria-label="Evidence" className="space-y-3">
          <h2 className="text-[13px] font-semibold">
            Evidence <span className="font-normal text-muted">({inv.evidence.length})</span>
          </h2>
          {inv.evidence.length === 0 ? (
            <p className="rounded-md border border-dashed border-line p-4 text-xs text-muted">
              Evidence collected by the agent will appear here.
            </p>
          ) : (
            inv.evidence.map((ev) => <EvidenceCard key={ev.id} evidence={ev} />)
          )}
        </section>
      </div>

      {inv.report && (
        <div className="mt-5">
          <ReportSection report={inv.report} investigationId={inv.id} />
        </div>
      )}
    </div>
  )
}
