import { useEffect, useState } from 'react'
import { BarChart3, Database, Moon, Sparkles, Sun } from 'lucide-react'
import { useApi } from './lib/hooks.js'
import DataTable from './components/DataTable.jsx'
import Predictor from './components/Predictor.jsx'
import Dashboard from './components/Dashboard.jsx'

const TABS = [
  { id: 'explorer', label: 'Explorer', icon: Database },
  { id: 'predictor', label: 'Predictor', icon: Sparkles },
  { id: 'insights', label: 'Insights', icon: BarChart3 },
]

export default function App() {
  const [tab, setTab] = useState('explorer')
  const [dark, setDark] = useState(() => localStorage.getItem('theme') !== 'light')
  const { data: meta, error, loading } = useApi('/meta', {})

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Tunisian Bac Analytics &amp; Prediction Engine</h1>
          <p className="text-sm text-slate-500">
            {meta ? `${meta.total_records} records · ${meta.year_min}–${meta.year_max}` : 'Loading dataset…'}
          </p>
        </div>
        <nav className="flex items-center gap-1 rounded-xl bg-slate-200 p-1 dark:bg-slate-800">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ${tab === id ? 'bg-white shadow dark:bg-slate-950' : 'text-slate-500'}`}>
              <Icon size={16} /> {label}
            </button>
          ))}
          <button onClick={() => setDark(!dark)} aria-label="Toggle theme" className="px-2 text-slate-500">
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </nav>
      </header>

      {error && <div className="card border-red-400 text-red-600">API unreachable: {error}. Is the backend running on :8000?</div>}
      {loading && !meta && <div className="card">Loading…</div>}
      {meta && (
        <main>
          {tab === 'explorer' && <DataTable meta={meta} />}
          {tab === 'predictor' && <Predictor meta={meta} />}
          {tab === 'insights' && <Dashboard meta={meta} />}
        </main>
      )}
    </div>
  )
}
