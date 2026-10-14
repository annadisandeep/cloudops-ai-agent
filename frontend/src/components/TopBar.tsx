import { useLocation, useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { useApp } from '../context/AppContext'
import { Select, type SelectOption } from './Select'

const TITLES: Array<[RegExp, string]> = [
  [/^\/$/, 'Overview'],
  [/^\/resources/, 'Resources'],
  [/^\/monitoring/, 'Monitoring'],
  [/^\/investigations\//, 'Investigation'],
  [/^\/investigate/, 'Investigate'],
  [/^\/history/, 'History'],
  [/^\/settings/, 'Settings'],
]

function pageTitle(pathname: string): string {
  for (const [pattern, title] of TITLES) {
    if (pattern.test(pathname)) return title
  }
  return 'CloudOps Agent'
}

export function TopBar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { config, providers, selectedProvider, selectedAccount, setSelectedProvider } =
    useApp()

  const options: SelectOption[] = providers.flatMap((p) => {
    if (!p.enabled) {
      return [
        {
          value: `${p.id}`,
          label: `${p.name} (not configured)`,
          disabled: true,
        },
      ]
    }
    if (p.accounts.length === 0) {
      return [{ value: p.id, label: p.name }]
    }
    return p.accounts.map((a) => ({
      value: `${p.id}:${a.id}`,
      label: `${p.name} / ${a.name}`,
    }))
  })

  const currentValue = selectedAccount
    ? `${selectedProvider}:${selectedAccount}`
    : selectedProvider

  const handleProviderChange = (value: string) => {
    const [provider, account] = value.split(':')
    setSelectedProvider(provider, account ?? null)
  }

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-line bg-bg px-4 md:px-6">
      <h1 className="text-sm font-semibold tracking-tight">
        {pageTitle(location.pathname)}
      </h1>
      <div className="flex items-center gap-2.5">
        {config?.demo_mode && (
          <span
            data-testid="demo-pill"
            className="hidden items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-2xs text-muted sm:inline-flex"
            title="The backend is running in demo mode with simulated data"
          >
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-warn" />
            Demo mode — simulated data
          </span>
        )}
        {options.length > 0 && (
          <Select
            label="Provider and account"
            value={
              options.some((o) => o.value === currentValue && !o.disabled)
                ? currentValue
                : (options.find((o) => !o.disabled)?.value ?? currentValue)
            }
            onChange={handleProviderChange}
            options={options}
            className="max-w-[220px]"
          />
        )}
        <button
          type="button"
          className="btn-primary"
          onClick={() => navigate('/investigate')}
        >
          <Plus size={13} aria-hidden="true" />
          New investigation
        </button>
      </div>
    </header>
  )
}
