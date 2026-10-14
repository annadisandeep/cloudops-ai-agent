import { Spinner } from './Spinner'

export type StatusKind =
  // investigation / step statuses
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  // resource statuses
  | 'stopped'
  | 'terminated'
  // severities
  | 'critical'
  | 'high'
  | 'medium'
  | 'low'
  // report scales
  | 'likely'
  | 'possible'
  | 'unlikely'
  | 'healthy'

const DOT: Record<string, string> = {
  queued: 'bg-muted',
  running: 'bg-warn',
  completed: 'bg-ok',
  failed: 'bg-crit',
  stopped: 'bg-muted',
  terminated: 'bg-crit',
  critical: 'bg-crit',
  high: 'bg-crit',
  medium: 'bg-warn',
  low: 'bg-muted',
  likely: 'bg-crit',
  possible: 'bg-warn',
  unlikely: 'bg-muted',
  healthy: 'bg-ok',
}

export function StatusBadge({
  status,
  label,
  showSpinner = false,
}: {
  status: string
  label?: string
  showSpinner?: boolean
}) {
  const key = status.toLowerCase()
  const dot = DOT[key] ?? 'bg-ok'
  const text = label ?? status
  return (
    <span
      data-testid="status-badge"
      className="inline-flex items-center gap-1.5 rounded border border-line bg-bg px-1.5 py-0.5 text-2xs font-medium text-fg"
    >
      {showSpinner && key === 'running' ? (
        <Spinner size={10} label="Running" />
      ) : (
        <span
          aria-hidden="true"
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`}
          data-testid="status-dot"
        />
      )}
      <span className="capitalize">{text}</span>
    </span>
  )
}

/** Plain dot + text (no border), used in dense table cells. */
export function StatusDot({ status, label }: { status: string; label?: string }) {
  const dot = DOT[status.toLowerCase()] ?? 'bg-ok'
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px]">
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`}
      />
      <span className="capitalize">{label ?? status}</span>
    </span>
  )
}
