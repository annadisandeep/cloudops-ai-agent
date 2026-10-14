import type { ReactElement, ReactNode } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AppContext, type AppContextValue } from '../context/AppContext'
import { fixtureConfig, fixtureProviders } from './fixtures'

export function makeAppValue(
  overrides: Partial<AppContextValue> = {},
): AppContextValue {
  return {
    config: fixtureConfig,
    providers: fixtureProviders,
    selectedProvider: 'demo',
    selectedAccount: 'demo-project',
    setSelectedProvider: () => {},
    theme: 'light',
    toggleTheme: () => {},
    bootstrapError: null,
    ...overrides,
  }
}

export function renderWithProviders(
  ui: ReactElement,
  {
    route = '/',
    path,
    appValue,
  }: { route?: string; path?: string; appValue?: Partial<AppContextValue> } = {},
) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <AppContext.Provider value={makeAppValue(appValue)}>
      <MemoryRouter initialEntries={[route]}>
        {path ? (
          <Routes>
            <Route path={path} element={children} />
          </Routes>
        ) : (
          children
        )}
      </MemoryRouter>
    </AppContext.Provider>
  )
  return render(ui, { wrapper })
}

export function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
