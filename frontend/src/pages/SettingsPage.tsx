import { Cloud, Cpu, Gauge, Moon, Sun } from 'lucide-react'
import { useApp } from '../context/AppContext'
import { Card } from '../components/Card'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { PageHeader } from '../components/PageHeader'
import { StatusDot } from '../components/StatusBadge'

const PROVIDER_LABELS: Record<string, string> = {
  demo: 'Demo Environment',
  gcp: 'Google Cloud Platform',
  aws: 'Amazon Web Services',
}

export function SettingsPage() {
  const { config, theme, toggleTheme } = useApp()

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Server configuration is read-only here — it is managed via environment variables on the backend."
      />

      <div className="grid max-w-4xl gap-4">
        <Card title="Appearance">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[13px] font-medium">Theme</p>
              <p className="text-xs text-muted">
                Stored in your browser. Follows system preference until changed.
              </p>
            </div>
            <button type="button" onClick={toggleTheme} className="btn-secondary">
              {theme === 'dark' ? (
                <Sun size={13} aria-hidden="true" />
              ) : (
                <Moon size={13} aria-hidden="true" />
              )}
              Switch to {theme === 'dark' ? 'light' : 'dark'}
            </button>
          </div>
        </Card>

        {!config ? (
          <Card title="Server configuration">
            <LoadingSkeleton rows={5} />
          </Card>
        ) : (
          <>
            <Card title="Mode">
              <div className="flex items-center gap-2 text-[13px]">
                <StatusDot
                  status={config.demo_mode ? 'medium' : 'healthy'}
                  label={config.demo_mode ? 'Demo mode — all data is simulated' : 'Live mode'}
                />
              </div>
            </Card>

            <Card title="Provider connections">
              <div className="grid gap-3 md:grid-cols-3">
                {Object.entries(config.providers).map(([id, p]) => (
                  <div key={id} className="rounded-md border border-line p-3">
                    <div className="flex items-center gap-2">
                      <Cloud size={14} aria-hidden="true" className="text-muted" />
                      <p className="text-[13px] font-medium">
                        {PROVIDER_LABELS[id] ?? id.toUpperCase()}
                      </p>
                    </div>
                    <div className="mt-2">
                      <StatusDot
                        status={p.enabled ? 'healthy' : 'stopped'}
                        label={p.enabled ? `Enabled (${p.mode})` : 'Not configured'}
                      />
                    </div>
                    {!p.enabled && (
                      <p className="mt-2 text-2xs text-muted">
                        Read-only live mode requires server-side credentials. See the
                        backend README for setup via environment variables.
                      </p>
                    )}
                    {p.allowed_projects && p.allowed_projects.length > 0 && (
                      <p className="mt-2 font-mono text-2xs text-muted">
                        projects: {p.allowed_projects.join(', ')}
                      </p>
                    )}
                    {p.allowed_accounts && p.allowed_accounts.length > 0 && (
                      <p className="mt-2 font-mono text-2xs text-muted">
                        accounts: {p.allowed_accounts.join(', ')}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </Card>

            <Card title="LLM provider">
              <div className="flex items-center gap-3">
                <Cpu size={14} aria-hidden="true" className="text-muted" />
                <div>
                  <p className="text-[13px] font-medium capitalize">{config.llm.provider}</p>
                  <p className="font-mono text-xs text-muted">{config.llm.model}</p>
                </div>
              </div>
              <p className="mt-2 text-2xs text-muted">
                Configured server-side. API keys never reach the browser.
              </p>
            </Card>

            <Card title="Limits">
              <ul className="space-y-1.5 text-[13px]">
                <li className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-muted">
                    <Gauge size={13} aria-hidden="true" />
                    Max agent steps per investigation
                  </span>
                  <span className="font-mono tnum">{config.limits.max_steps}</span>
                </li>
                <li className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-muted">
                    <Gauge size={13} aria-hidden="true" />
                    Tool timeout
                  </span>
                  <span className="font-mono tnum">{config.limits.tool_timeout_seconds}s</span>
                </li>
                <li className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-muted">
                    <Gauge size={13} aria-hidden="true" />
                    Investigation timeout
                  </span>
                  <span className="font-mono tnum">
                    {config.limits.investigation_timeout_seconds}s
                  </span>
                </li>
              </ul>
            </Card>
          </>
        )}
      </div>
    </div>
  )
}
