import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { useApp } from '../context/AppContext'

export function AppShell() {
  const { bootstrapError } = useApp()
  return (
    <div className="min-h-screen bg-bg">
      <Sidebar />
      <div className="pl-14 md:pl-[232px]">
        <TopBar />
        {bootstrapError && (
          <div
            role="alert"
            className="border-b border-line bg-surface px-6 py-2 text-xs text-muted"
          >
            Could not load server configuration ({bootstrapError}). Some features
            may be unavailable until the backend is reachable.
          </div>
        )}
        <main className="mx-auto max-w-content px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
