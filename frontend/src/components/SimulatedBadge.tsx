export function SimulatedBadge() {
  return (
    <span
      data-testid="simulated-badge"
      className="inline-flex items-center gap-1 rounded border border-line bg-surface px-1.5 py-0.5 text-2xs text-muted"
      title="This data is simulated (demo mode)"
    >
      <span aria-hidden="true" className="h-1 w-1 rounded-full bg-warn" />
      Simulated
    </span>
  )
}
