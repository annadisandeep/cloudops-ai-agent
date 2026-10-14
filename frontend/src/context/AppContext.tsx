/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { getConfig, getProviders } from '../api/client'
import type { AppConfig, Provider } from '../api/types'

export type Theme = 'light' | 'dark'

const THEME_KEY = 'cloudops-theme'
const PROVIDER_KEY = 'cloudops-provider'
const ACCOUNT_KEY = 'cloudops-account'

export interface AppContextValue {
  config: AppConfig | null
  providers: Provider[]
  selectedProvider: string
  selectedAccount: string | null
  setSelectedProvider: (provider: string, account?: string | null) => void
  theme: Theme
  toggleTheme: () => void
  bootstrapError: string | null
}

export const AppContext = createContext<AppContextValue | null>(null)

function initialTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    if (stored === 'dark' || stored === 'light') return stored
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark'
    }
  } catch {
    // localStorage unavailable
  }
  return 'light'
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [providers, setProviders] = useState<Provider[]>([])
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [selectedProvider, setSelectedProviderState] = useState<string>(() => {
    try {
      return localStorage.getItem(PROVIDER_KEY) ?? 'demo'
    } catch {
      return 'demo'
    }
  })
  const [selectedAccount, setSelectedAccount] = useState<string | null>(() => {
    try {
      return localStorage.getItem(ACCOUNT_KEY)
    } catch {
      return null
    }
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // ignore
    }
  }, [theme])

  useEffect(() => {
    let cancelled = false
    Promise.all([getConfig(), getProviders()])
      .then(([cfg, prov]) => {
        if (cancelled) return
        setConfig(cfg)
        setProviders(prov.items)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setBootstrapError(
          err instanceof Error ? err.message : 'Failed to load configuration',
        )
      })
    return () => {
      cancelled = true
    }
  }, [])

  const setSelectedProvider = useCallback(
    (provider: string, account?: string | null) => {
      setSelectedProviderState(provider)
      const nextAccount = account ?? null
      setSelectedAccount(nextAccount)
      try {
        localStorage.setItem(PROVIDER_KEY, provider)
        if (nextAccount) localStorage.setItem(ACCOUNT_KEY, nextAccount)
        else localStorage.removeItem(ACCOUNT_KEY)
      } catch {
        // ignore
      }
    },
    [],
  )

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  const value = useMemo<AppContextValue>(
    () => ({
      config,
      providers,
      selectedProvider,
      selectedAccount,
      setSelectedProvider,
      theme,
      toggleTheme,
      bootstrapError,
    }),
    [
      config,
      providers,
      selectedProvider,
      selectedAccount,
      setSelectedProvider,
      theme,
      toggleTheme,
      bootstrapError,
    ],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
