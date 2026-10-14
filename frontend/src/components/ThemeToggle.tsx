import { Moon, Sun } from 'lucide-react'
import { useApp } from '../context/AppContext'

export function ThemeToggle({ className = '' }: { className?: string }) {
  const { theme, toggleTheme } = useApp()
  const next = theme === 'dark' ? 'light' : 'dark'
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className={`rounded p-1.5 transition-colors duration-150 ${className}`}
    >
      {theme === 'dark' ? (
        <Sun size={15} aria-hidden="true" />
      ) : (
        <Moon size={15} aria-hidden="true" />
      )}
    </button>
  )
}
