const STAGES = [
  { id: 'parsing', label: 'Parsing inputs' },
  { id: 'entities', label: 'Extracting company & role' },
  { id: 'searching', label: 'Searching the web' },
  { id: 'reading', label: 'Reading sources' },
  { id: 'questions', label: 'Finding common questions' },
  { id: 'ranking', label: 'Ranking by frequency' },
  { id: 'answering', label: 'Writing tailored answers' },
]

const STAGE_ORDER = Object.fromEntries(STAGES.map((s, i) => [s.id, i]))
STAGE_ORDER.cache = STAGES.length
STAGE_ORDER.done = STAGES.length

export default function ProgressView({ events }) {
  const last = events[events.length - 1] || { stage: 'parsing', message: 'Starting…', pct: 0 }
  const currentIdx = STAGE_ORDER[last.stage] ?? 0
  // Latest message per stage, so completed rows keep their final counts.
  const latestByStage = {}
  for (const e of events) latestByStage[e.stage] = e.message

  return (
    <div className="mx-auto max-w-xl">
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-5">
          <div className="mb-1 flex justify-between text-sm">
            <span className="font-medium text-slate-700">Researching…</span>
            <span className="text-slate-400">{last.pct}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-accent-600 transition-all duration-500"
              style={{ width: `${last.pct}%` }}
            />
          </div>
        </div>

        <ul className="space-y-3">
          {STAGES.map((stage, i) => {
            const state = i < currentIdx ? 'done' : i === currentIdx ? 'active' : 'pending'
            return (
              <li key={stage.id} className="flex items-start gap-3">
                <span
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs ${
                    state === 'done'
                      ? 'bg-emerald-100 text-emerald-600'
                      : state === 'active'
                        ? 'bg-accent-100 text-accent-700'
                        : 'bg-slate-100 text-slate-300'
                  }`}
                >
                  {state === 'done' ? '✓' : state === 'active' ? <Spinner /> : '·'}
                </span>
                <div className="min-w-0">
                  <p
                    className={`text-sm ${
                      state === 'pending' ? 'text-slate-400' : 'font-medium text-slate-700'
                    }`}
                  >
                    {stage.label}
                  </p>
                  {state !== 'pending' && latestByStage[stage.id] && (
                    <p className="truncate text-xs text-slate-400">{latestByStage[stage.id]}</p>
                  )}
                </div>
              </li>
            )
          })}
        </ul>

        <p className="mt-5 text-center text-xs text-slate-400">
          Everything runs locally — research can take a few minutes, answers longest.
        </p>
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}
