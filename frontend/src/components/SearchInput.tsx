import { Search } from 'lucide-react'

export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  label = 'Search',
  className = '',
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  label?: string
  className?: string
}) {
  return (
    <div className={`relative ${className}`}>
      <Search
        size={13}
        aria-hidden="true"
        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted"
      />
      <input
        type="search"
        role="searchbox"
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="input-base w-full pl-7"
      />
    </div>
  )
}
