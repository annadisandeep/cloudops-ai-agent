import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { createInvestigation, getScenarios, listResources } from '../api/client'
import type { Scenario } from '../api/types'
import { useApi } from '../hooks/useApi'
import { useApp } from '../context/AppContext'
import { ErrorState } from '../components/ErrorState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { PageHeader } from '../components/PageHeader'
import { ProviderBadge } from '../components/ProviderBadge'
import { Select } from '../components/Select'
import { SimulatedBadge } from '../components/SimulatedBadge'
import { Spinner } from '../components/Spinner'
import { StatusDot } from '../components/StatusBadge'

interface PrefillState {
  scenarioId?: string | null
  resourceId?: string | null
  provider?: string | null
}

function ScenarioCard({
  scenario,
  selected,
  onSelect,
}: {
  scenario: Scenario
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`w-full rounded-md border p-3 text-left transition-colors duration-150 ${
        selected
          ? 'border-fg bg-surface'
          : 'border-line hover:bg-surface'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-2">
          <StatusDot status={scenario.severity} label="" />
          <span className="text-[13px] font-medium">{scenario.title}</span>
        </span>
        <ProviderBadge provider={scenario.provider} />
      </div>
      <p className="mt-1.5 line-clamp-2 text-xs text-muted">{scenario.description}</p>
      <div className="mt-2 flex items-center gap-2">
        <span className="font-mono text-2xs text-muted">{scenario.resource_name}</span>
        {scenario.simulated && <SimulatedBadge />}
      </div>
    </button>
  )
}

export function InvestigatePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const prefill = (location.state ?? {}) as PrefillState
  const { selectedProvider, selectedAccount, providers } = useApp()

  const [question, setQuestion] = useState('')
  const [mode, setMode] = useState<'scenario' | 'manual'>(
    prefill.resourceId && !prefill.scenarioId ? 'manual' : 'scenario',
  )
  const [scenarioId, setScenarioId] = useState<string | null>(prefill.scenarioId ?? null)
  const [manualProvider, setManualProvider] = useState(prefill.provider ?? selectedProvider)
  const [manualResource, setManualResource] = useState(prefill.resourceId ?? '')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const scenarios = useApi(() => getScenarios(), [])
  const manualResources = useApi(
    () =>
      listResources({
        provider: manualProvider,
        account: manualProvider === selectedProvider ? (selectedAccount ?? undefined) : undefined,
        page_size: 100,
      }),
    [manualProvider, selectedProvider, selectedAccount],
  )

  const selectedScenario = useMemo(
    () => scenarios.data?.items.find((s) => s.id === scenarioId) ?? null,
    [scenarios.data, scenarioId],
  )

  // If navigated here with a scenario prefill, adopt its suggested question.
  useEffect(() => {
    if (selectedScenario && question === '') {
      setQuestion(selectedScenario.suggested_question)
    }
    // Only when the selected scenario changes — intentionally not on question edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedScenario])

  const suggestions = (scenarios.data?.items ?? [])
    .slice(0, 4)
    .map((s) => ({ id: s.id, question: s.suggested_question }))

  const canSubmit =
    question.trim().length > 0 &&
    !submitting &&
    (mode === 'scenario' ? scenarioId !== null : manualResource !== '')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const body =
        mode === 'scenario' && selectedScenario
          ? {
              question: question.trim(),
              provider: 'demo',
              scenario_id: selectedScenario.id,
              resource_id: selectedScenario.resource_id,
              time_window: selectedScenario.time_window,
            }
          : {
              question: question.trim(),
              provider: manualProvider,
              resource_id: manualResource,
            }
      const investigation = await createInvestigation(body)
      navigate(`/investigations/${investigation.id}`)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to start investigation')
      setSubmitting(false)
    }
  }

  const providerOptions = providers
    .filter((p) => p.enabled)
    .map((p) => ({ value: p.id, label: p.name }))

  return (
    <div>
      <PageHeader
        title="Investigate"
        description="Ask the agent to diagnose an incident across metrics, logs and metadata"
      />

      <form onSubmit={handleSubmit} className="flex flex-col gap-6 lg:flex-row">
        {/* Left column — question + submit */}
        <div className="w-full shrink-0 space-y-4 lg:w-[380px]">
          <div className="rounded-md border border-line bg-bg p-4">
            <h2 className="text-[13px] font-semibold">Start investigation</h2>
            <label htmlFor="inv-question" className="mt-3 block text-xs text-muted">
              What do you want to find out?
            </label>
            <textarea
              id="inv-question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={4}
              placeholder="e.g. Why is my GCP VM experiencing high CPU utilization?"
              className="input-base mt-1.5 w-full resize-y"
            />
            {suggestions.length > 0 && (
              <div className="mt-2.5">
                <p className="mb-1.5 text-2xs text-muted">Suggested questions</p>
                <div className="flex flex-wrap gap-1.5">
                  {suggestions.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => {
                        setQuestion(s.question)
                        setMode('scenario')
                        setScenarioId(s.id)
                      }}
                      className="rounded border border-line px-2 py-1 text-left text-2xs text-muted transition-colors duration-150 hover:bg-surface hover:text-fg"
                    >
                      {s.question}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-4 border-t border-line pt-3">
              <div
                role="tablist"
                aria-label="Target selection mode"
                className="inline-flex rounded border border-line p-0.5"
              >
                {(['scenario', 'manual'] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    role="tab"
                    aria-selected={mode === m}
                    onClick={() => setMode(m)}
                    className={`rounded px-2.5 py-1 text-xs font-medium capitalize transition-colors duration-150 ${
                      mode === m ? 'bg-fg text-bg' : 'text-muted hover:text-fg'
                    }`}
                  >
                    {m === 'scenario' ? 'Demo scenario' : 'Manual'}
                  </button>
                ))}
              </div>

              {mode === 'manual' && (
                <div className="mt-3 space-y-2.5">
                  <Select
                    label="Provider"
                    value={manualProvider}
                    onChange={(v) => {
                      setManualProvider(v)
                      setManualResource('')
                    }}
                    options={
                      providerOptions.length > 0
                        ? providerOptions
                        : [{ value: selectedProvider, label: selectedProvider }]
                    }
                    className="w-full"
                  />
                  {manualResources.loading ? (
                    <LoadingSkeleton rows={1} />
                  ) : (
                    <Select
                      label="Resource"
                      value={manualResource}
                      onChange={setManualResource}
                      options={[
                        { value: '', label: 'Select a resource…', disabled: true },
                        ...(manualResources.data?.items ?? []).map((r) => ({
                          value: r.id,
                          label: r.name,
                        })),
                      ]}
                      className="w-full"
                    />
                  )}
                </div>
              )}

              {mode === 'scenario' && selectedScenario && (
                <p className="mt-3 text-xs text-muted">
                  Target: <span className="font-mono text-fg">{selectedScenario.resource_id}</span>{' '}
                  · window {new Date(selectedScenario.time_window.start).toISOString().slice(11, 16)}
                  –{new Date(selectedScenario.time_window.end).toISOString().slice(11, 16)} UTC
                </p>
              )}
              {mode === 'scenario' && !selectedScenario && (
                <p className="mt-3 text-xs text-muted">Select a scenario on the right.</p>
              )}
            </div>

            {submitError && (
              <p role="alert" className="mt-3 text-xs text-crit">
                {submitError}
              </p>
            )}

            <button
              type="submit"
              disabled={!canSubmit}
              className="btn-primary mt-4 w-full justify-center"
            >
              {submitting && <Spinner size={12} label="Starting" />}
              {submitting ? 'Starting…' : 'Start investigation'}
            </button>
          </div>
        </div>

        {/* Right column — scenario cards */}
        <div className="min-w-0 flex-1">
          {mode === 'scenario' ? (
            scenarios.loading ? (
              <LoadingSkeleton rows={8} />
            ) : scenarios.error ? (
              <ErrorState message={scenarios.error} onRetry={scenarios.retry} />
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {(scenarios.data?.items ?? []).map((s) => (
                  <ScenarioCard
                    key={s.id}
                    scenario={s}
                    selected={s.id === scenarioId}
                    onSelect={() => {
                      setScenarioId(s.id)
                      if (question.trim() === '') setQuestion(s.suggested_question)
                    }}
                  />
                ))}
              </div>
            )
          ) : (
            <div className="rounded-md border border-dashed border-line p-6 text-xs text-muted">
              Manual mode: pick a provider and resource on the left. The agent will choose
              which metrics, logs and metadata to inspect based on your question.
            </div>
          )}
        </div>
      </form>
    </div>
  )
}
