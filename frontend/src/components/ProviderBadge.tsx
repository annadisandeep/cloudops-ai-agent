export function ProviderBadge({ provider }: { provider: string }) {
  return (
    <span
      data-testid="provider-badge"
      className="inline-flex items-center rounded border border-line px-1.5 py-0.5 font-mono text-2xs font-medium uppercase tracking-wide text-muted"
    >
      {provider}
    </span>
  )
}
