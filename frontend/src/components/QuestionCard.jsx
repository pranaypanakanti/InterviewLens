import { useState } from 'react'

const CATEGORY_COLORS = {
  technical: 'bg-sky-50 text-sky-700 border-sky-200',
  coding: 'bg-violet-50 text-violet-700 border-violet-200',
  'system-design': 'bg-cyan-50 text-cyan-700 border-cyan-200',
  behavioral: 'bg-rose-50 text-rose-700 border-rose-200',
  'role-specific': 'bg-emerald-50 text-emerald-700 border-emerald-200',
  'domain-knowledge': 'bg-amber-50 text-amber-700 border-amber-200',
}

export default function QuestionCard({ q, index }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left hover:bg-slate-50"
      >
        <div className="min-w-0">
          <p className="font-medium text-slate-800">
            <span className="mr-2 text-slate-400">{index}.</span>
            {q.question}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                CATEGORY_COLORS[q.category] || 'bg-slate-50 text-slate-600 border-slate-200'
              }`}
            >
              {q.category}
            </span>
            {q.is_generic ? (
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs text-slate-500">
                generic (role/skill-based)
              </span>
            ) : (
              <span className="rounded-full border border-accent-100 bg-accent-50 px-2.5 py-0.5 text-xs font-medium text-accent-700">
                seen in {q.frequency} source{q.frequency > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
        <span className={`mt-1 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`}>
          ▾
        </span>
      </button>

      {open && (
        <div className="border-t border-slate-100 px-5 py-4">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{q.answer}</p>
          {q.why_asked && (
            <p className="mt-3 text-sm text-slate-500">
              <span className="font-semibold text-slate-600">Why they ask this: </span>
              {q.why_asked}
            </p>
          )}
          {q.tips && (
            <p className="mt-2 text-sm text-slate-500">
              <span className="font-semibold text-slate-600">Tips: </span>
              {q.tips}
            </p>
          )}
          {q.sources?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {q.sources.map((s) => (
                <a
                  key={s}
                  href={s}
                  target="_blank"
                  rel="noreferrer"
                  className="max-w-full truncate rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-accent-700 hover:border-accent-500"
                  title={s}
                >
                  {hostOf(s)}
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function hostOf(url) {
  try {
    return new URL(url).host.replace(/^www\./, '')
  } catch {
    return url
  }
}
