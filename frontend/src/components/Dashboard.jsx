import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi } from '../lib/hooks.js'

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#84cc16', '#f43f5e']
const short = (s, n = 28) => (s.length > n ? s.slice(0, n - 1) + '…' : s)

export default function Dashboard({ meta }) {
  const [subject, setSubject] = useState(meta.subjects.includes('Français') ? 'Français' : meta.subjects[0])
  const [branch, setBranch] = useState('')
  const [years, setYears] = useState(15)
  const [level, setLevel] = useState('unit')
  const top = useApi('/insights/top-themes', { subject, branch, years, limit: 12, level })
  const evo = useApi('/insights/evolution', { subject, branch, limit: 6, level })

  const evoRows = evo.data?.years.map((y, i) => ({ year: y, ...Object.fromEntries(evo.data.series.map((s) => [s.theme, s.data[i]])) })) ?? []

  return (
    <div className="space-y-4">
      <div className="card grid gap-3 sm:grid-cols-4">
        <label className="text-xs text-slate-500">Subject
          <select className="input mt-1" value={subject} onChange={(e) => setSubject(e.target.value)}>{meta.subjects.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label className="text-xs text-slate-500">Branch
          <select className="input mt-1" value={branch} onChange={(e) => setBranch(e.target.value)}><option value="">All branches</option>{meta.branches.map((b) => <option key={b}>{b}</option>)}</select></label>
        <label className="text-xs text-slate-500">Level
          <select className="input mt-1" value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="unit">Chapter / unit</option><option value="theme">Detailed theme</option></select></label>
        <label className="text-xs text-slate-500">Look-back window: {years} years
          <input type="range" min={5} max={19} value={years} onChange={(e) => setYears(+e.target.value)} className="mt-3 w-full" /></label>
      </div>

      <section className="card">
        <h2 className="mb-1 font-semibold">Most recurring themes</h2>
        <p className="mb-3 text-xs text-slate-500">
          Share of sittings (year × session) featuring each theme, {top.data?.from}–{top.data?.to} ({top.data?.total_slots ?? 0} sittings).
        </p>
        {top.error && <p className="text-red-600">{top.error}</p>}
        {top.data?.themes.length === 0 && <p className="text-slate-500">No data for this selection.</p>}
        {top.data?.themes.length > 0 && (
          <ResponsiveContainer width="100%" height={Math.max(220, top.data.themes.length * 32)}>
            <BarChart data={top.data.themes.map((t) => ({ ...t, name: short(t.theme), pct: Math.round(t.share * 100) }))} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
              <XAxis type="number" unit="%" domain={[0, 100]} />
              <YAxis type="category" dataKey="name" width={190} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v, _n, p) => [`${v}% (${p.payload.count} sittings)`, 'Share']} />
              <Bar dataKey="pct" fill="#6366f1" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>)}
      </section>

      <section className="card">
        <h2 className="mb-1 font-semibold">Evolution over time</h2>
        <p className="mb-3 text-xs text-slate-500">Occurrences per year of the main themes (Principale + Contrôle). Pick Français or Anglais to follow essay themes.</p>
        {evoRows.length > 0 && (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={evoRows}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
              <XAxis dataKey="year" /><YAxis allowDecimals={false} />
              <Tooltip /><Legend formatter={(v) => short(v, 24)} />
              {evo.data.series.map((s, i) => <Line key={s.theme} type="monotone" dataKey={s.theme} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={{ r: 2 }} />)}
            </LineChart>
          </ResponsiveContainer>)}
      </section>
    </div>
  )
}
