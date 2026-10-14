import { NavLink } from 'react-router-dom'
import {
  Activity,
  Clock,
  LayoutDashboard,
  Search,
  Server,
  Settings,
} from 'lucide-react'
import { ThemeToggle } from './ThemeToggle'

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/resources', label: 'Resources', icon: Server, end: false },
  { to: '/monitoring', label: 'Monitoring', icon: Activity, end: false },
  { to: '/investigate', label: 'Investigate', icon: Search, end: false },
  { to: '/history', label: 'History', icon: Clock, end: false },
  { to: '/settings', label: 'Settings', icon: Settings, end: false },
]

export function Sidebar({ version }: { version?: string }) {
  return (
    <aside
      aria-label="Primary navigation"
      className="fixed inset-y-0 left-0 z-30 flex w-14 flex-col bg-sidebar text-neutral-400 md:w-[232px]"
    >
      <div className="flex h-14 items-center px-4">
        <span className="hidden select-none text-[13px] font-semibold tracking-tight text-white md:block">
          CloudOps Agent
        </span>
        <span className="select-none text-[13px] font-semibold text-white md:hidden">
          C
        </span>
      </div>
      <nav className="flex-1 space-y-0.5 px-2 pt-2" aria-label="Main">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded px-2.5 py-1.5 text-[13px] transition-colors duration-150 ${
                isActive
                  ? 'bg-sidebar-active text-white'
                  : 'hover:bg-sidebar-hover hover:text-neutral-200'
              }`
            }
          >
            <Icon size={15} aria-hidden="true" className="shrink-0" />
            <span className="hidden md:inline">{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="flex items-center justify-between px-3 py-3">
        <ThemeToggle className="text-neutral-400 hover:bg-sidebar-hover hover:text-white" />
        <span className="hidden font-mono text-2xs text-neutral-500 md:inline">
          v{version ?? '0.1.0'}
        </span>
      </div>
    </aside>
  )
}
