import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download, Search } from 'lucide-react'
import { useApi, useDebounce } from '../lib/hooks.js'
import { exportUrl } from '../lib/api.js'

const COLS = [
  { key: 'year', label: 'Year' }, { key: 'session', label: 'Session' },
  { key: 'branch', label: 'Branch' }, { key: 'subject', label: 'Subject' }, { key: 'theme', label: 'Chapters / Themes' },
]

function Select({ label, value, onChange, options }) {
  return (
    <label className="text-xs text-slate-500">{label}
      <select className="input mt-1" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {options.map((o) => <option key={o}>{o}</option>)}
      </select>
    </label>
  )
}

export default function DataTable({ meta }) {
  const [f, setF] = useState({ branch: '', subject: '', session: '', year_min: meta.year_min, year_max: meta.year_max })
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState({ by: 'year', order: 'desc' })
  const [page, setPage] = useState(1)
  const q = useDebounce(search, 300)
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: v }))

  useEffect(() => setPage(1), [f, q, sort])   // any criteria change returns to page 1

  // Subjects/sessions offered depend on the other selections so users never reach empty combos.
  const subjects = f.branch ? meta.subjects_by_branch[f.branch] : meta.subjects
  const sessions = f.subject ? meta.sessions_by_subject[f.subject] : meta.sessions
  const yearsInvalid = Number(f.year_min) > Number(f.year_max)
  const params = { branch: f.branch, subject: f.subject, session: f.session, year_min: f.year_min, year_max: f.year_max, q }
  const { data, error, loading } = useApi('/records', { ...params, sort_by: sort.by, order: sort.order, page, page_size: 25 }, !yearsInvalid)

  const toggleSort = (key) => setSort((s) => ({ by: key, order: s.by === key && s.order === 'desc' ? 'asc' : 'desc' }))

  return (
    <div className="space-y-4">
      <div className="card grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <label className="relative text-xs text-slate-500 lg:col-span-2">Search chapters / themes
          <Search size={14} className="absolute left-3 top-8 text-slate-400" />
          <input className="input mt-1 pl-8" placeholder="e.g. matrice, ecodriving, الدولة…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>
        <Select label="Branch" value={f.branch} onChange={set('branch')} options={meta.branches} />
        <Select label="Subject" value={f.subject} onChange={set('subject')} options={subjects} />
        <Select label="Session" value={f.session} onChange={set('session')} options={sessions} />
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-slate-500">From
            <input type="number" className="input mt-1" min={meta.year_min} max={meta.year_max} value={f.year_min} onChange={(e) => set('year_min')(e.target.value)} /></label>
          <label className="text-xs text-slate-500">To
            <input type="number" className="input mt-1" min={meta.year_min} max={meta.year_max} value={f.year_max} onChange={(e) => set('year_max')(e.target.value)} /></label>
        </div>
      </div>
      {yearsInvalid && <p className="text-sm text-amber-600">“From” year must not exceed “To” year.</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card overflow-x-auto p-0">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2 text-sm dark:border-slate-800">
          <span className="text-slate-500">{loading ? 'Searching…' : `${data?.total ?? 0} results`}</span>
          <a className="btn" href={exportUrl(params)} download><Download size={14} /> Export CSV</a>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-100 text-xs uppercase text-slate-500 dark:bg-slate-800/60">
            <tr>{COLS.map((c) => (
              <th key={c.key} className="cursor-pointer select-none px-4 py-2" onClick={() => toggleSort(c.key)}>
                <span className="inline-flex items-center gap-1">{c.label}
                  {sort.by === c.key && (sort.order === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}</span>
              </th>))}</tr>
          </thead>
          <tbody>
            {data?.rows.map((r, i) => (
              <tr key={i} className="border-t border-slate-100 dark:border-slate-800">
                <td className="px-4 py-2 tabular-nums">{r.year}</td>
                <td className="px-4 py-2">{r.session}</td>
                <td className="px-4 py-2">{r.branch.replace('Bac ', '')}</td>
                <td className="px-4 py-2" dir="auto">{r.subject}</td>
                <td className="px-4 py-2" dir="auto">{r.theme}</td>
              </tr>))}
            {data && data.rows.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-500">No record matches these filters.</td></tr>)}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft size={14} /></button>
          <span>Page {data.page} / {data.pages}</span>
          <button className="btn" disabled={page >= data.pages} onClick={() => setPage(page + 1)}><ChevronRight size={14} /></button>
        </div>)}
    </div>
  )
}
