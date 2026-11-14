import { useState } from 'react'
import { AlertTriangle, CalendarClock, Target } from 'lucide-react'
import { useApi } from '../lib/hooks.js'

const BADGE = {
  'High Probability': 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  'Cyclically Due': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300',
  Moderate: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  Low: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
}
const COMP = { recency: 'Recency', due: 'Gap / due', coverage: 'Curriculum weight', markov: 'Markov' }

function Backtest({ bt }) {
  if (!bt?.folds) return <p className="text-xs text-slate-500">{bt?.note || 'Backtest unavailable.'}</p>
  const pct = (x) => `${Math.round(x * 100)}%`
  const useful = bt.model >= 0.6
  const beatsFreq = bt.model > bt.frequency_baseline + 0.02
  return (
    <div className={`card text-sm ${useful ? '' : 'border-amber-400'}`}>
      <div className="mb-1 flex items-center gap-2 font-medium">
        {useful ? <Target size={16} /> : <AlertTriangle size={16} className="text-amber-500" />}
        Historical reliability (walk-forward on the last {bt.folds} sittings)
      </div>
      <p className="text-slate-600 dark:text-slate-400">
        Chance that a chapter that really appeared is ranked above one that did not: model <b>{pct(bt.model)}</b> ·
        frequency-only <b>{pct(bt.frequency_baseline)}</b> · random guessing <b>{pct(bt.random)}</b>.
        {!useful && ' Close to random here: treat the ranking as weak evidence.'}
        {useful && !beatsFreq && ' The ranking mostly reflects how often a chapter appears; recency and cycles add little for this subject.'}
      </p>
    </div>
  )
}

export default function Predictor({ meta }) {
  const [branch, setBranch] = useState(meta.branches[0])
  const subjects = meta.subjects_by_branch[branch]
  const [subject, setSubject] = useState(subjects[0])
  const [session, setSession] = useState('')
  const [level, setLevel] = useState('unit')
  const sessions = meta.sessions_by_subject[subject] || []

  const changeBranch = (b) => { setBranch(b); const s = meta.subjects_by_branch[b]; if (!s.includes(subject)) { setSubject(s[0]); setSession('') } }
  const changeSubject = (s) => { setSubject(s); setSession('') }

  const { data, error, loading } = useApi('/predict', { branch, subject, session: sessions.includes(session) ? session : '', top_n: 10, level })

  return (
    <div className="space-y-4">
      <div className="card grid gap-3 sm:grid-cols-4">
        <label className="text-xs text-slate-500">Branch
          <select className="input mt-1" value={branch} onChange={(e) => changeBranch(e.target.value)}>{meta.branches.map((b) => <option key={b}>{b}</option>)}</select></label>
        <label className="text-xs text-slate-500">Subject
          <select className="input mt-1" value={subject} onChange={(e) => changeSubject(e.target.value)}>{subjects.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label className="text-xs text-slate-500">Target session
          <select className="input mt-1" value={session || sessions[0]} onChange={(e) => setSession(e.target.value)}>{sessions.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label className="text-xs text-slate-500">Level
          <select className="input mt-1" value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="unit">Chapter / unit (recommended)</option>
            <option value="theme">Detailed theme</option>
          </select></label>
      </div>

      {error && <div className="card border-red-400 text-red-600">{error}</div>}
      {loading && <div className="card">Computing…</div>}
      {data && !loading && (
        <>
          <div className="card flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
            <span className="flex items-center gap-2 font-semibold"><CalendarClock size={16} /> Forecast for {data.target_year} · {data.target_session}</span>
            <span className="text-slate-500">{data.history_slots} past sittings · {data.candidates} candidate themes · ≈{data.expected_themes_per_slot} themes per sitting · history: {data.history_reliability}</span>
          </div>
          <Backtest bt={data.backtest} />
          {data.predictions.length === 0 && <div className="card text-slate-500">Not enough usable theme data for this selection.</div>}
          <ol className="space-y-3">
            {data.predictions.map((p) => (
              <li key={p.theme} className="card">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="mr-2 text-slate-400">#{p.rank}</span>
                    <span className="font-semibold" dir="auto">{p.theme}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${BADGE[p.label]}`}>{p.label}</span>
                    <span className="text-lg font-bold tabular-nums">{Math.round(p.probability * 100)}%</span>
                  </div>
                </div>
                <div className="my-2 h-2 overflow-hidden rounded bg-slate-200 dark:bg-slate-800">
                  <div className="h-full bg-indigo-500" style={{ width: `${Math.min(100, p.probability * 100)}%` }} />
                </div>
                <p className="text-xs text-slate-500">
                  {p.appearances}× seen · last {p.last_seen} · {p.gap_slots} sitting(s) since
                  {p.mean_interval_slots ? ` · usual interval ≈ ${p.mean_interval_slots} sittings` : ''}
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {p.years.map((y, i) => <span key={i} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs tabular-nums dark:bg-slate-800">{y}</span>)}
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                  {Object.entries(p.breakdown).map(([k, v]) => (
                    <div key={k}><div className="text-slate-500">{COMP[k]}</div>
                      <div className="h-1.5 rounded bg-slate-200 dark:bg-slate-800"><div className="h-full rounded bg-emerald-500" style={{ width: `${v * 100}%` }} /></div></div>))}
                </div>
              </li>))}
          </ol>
          <p className="text-xs text-slate-500">
            Probabilities are heuristic estimates from past patterns in this dataset. Syllabus changes, reforms or excluded chapters are not visible to the model. Use them to prioritise revision, never to skip chapters.
          </p>
        </>
      )}
    </div>
  )
}
