import type { ReactNode } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

export interface Column<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  className?: string
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  'aria-label': ariaLabel,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  onRowClick?: (row: T) => void
  'aria-label'?: string
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full border-collapse text-left" aria-label={ariaLabel}>
        <thead>
          <tr className="border-b border-line bg-surface">
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={`px-3 py-2 text-2xs font-medium uppercase tracking-wide text-muted ${col.className ?? ''}`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={
                onRowClick
                  ? (e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        onRowClick(row)
                      }
                    }
                  : undefined
              }
              tabIndex={onRowClick ? 0 : undefined}
              className={`border-b border-line last:border-b-0 ${
                onRowClick
                  ? 'cursor-pointer transition-colors duration-150 hover:bg-surface focus-visible:bg-surface'
                  : ''
              }`}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`px-3 py-2 align-middle text-[13px] ${col.className ?? ''}`}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)
  const lastPage = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="flex items-center justify-between py-2.5 text-xs text-muted">
      <span className="tnum">
        {start}–{end} of {total}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="rounded border border-line p-1 transition-colors duration-150 enabled:hover:bg-surface disabled:opacity-40"
        >
          <ChevronLeft size={14} aria-hidden="true" />
        </button>
        <span className="px-1.5 tnum">
          {page} / {lastPage}
        </span>
        <button
          type="button"
          aria-label="Next page"
          disabled={page >= lastPage}
          onClick={() => onPageChange(page + 1)}
          className="rounded border border-line p-1 transition-colors duration-150 enabled:hover:bg-surface disabled:opacity-40"
        >
          <ChevronRight size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
