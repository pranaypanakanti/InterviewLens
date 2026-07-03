import { useCallback, useEffect, useRef, useState } from 'react'
import InputPanel from './components/InputPanel'
import ProgressView from './components/ProgressView'
import ResultsView from './components/ResultsView'
import { fetchHealth, fetchResult, startAnalysis, subscribeToJob } from './api'

export default function App() {
  const [view, setView] = useState('input') // input | progress | results
  const [events, setEvents] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [health, setHealth] = useState(null)
  const esRef = useRef(null)

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setHealth({ unreachable: true }))
    return () => esRef.current && esRef.current.close()
  }, [])

  const research = useCallback(async ({ jdText, resumeFile, mode, force }) => {
    setError(null)
    setEvents([])
    setResult(null)
    try {
      const jobId = await startAnalysis({ jdText, resumeFile, mode, force })
      setView('progress')
      esRef.current = subscribeToJob(
        jobId,
        async (event) => {
          setEvents((prev) => [...prev, event])
          if (event.stage === 'done') {
            esRef.current.close()
            const res = await fetchResult(jobId)
            setResult(res.result)
            setView('results')
          } else if (event.stage === 'error') {
            esRef.current.close()
            setError(event.message)
            setView('input')
          }
        },
        async () => {
          // Stream dropped — poll the result once in case the job finished anyway.
          try {
            const res = await fetchResult(jobId)
            if (res.status === 'done') {
              setResult(res.result)
              setView('results')
              return
            }
          } catch {
            /* fall through */
          }
          setError('Lost connection to the research job.')
          setView('input')
        },
      )
    } catch (e) {
      setError(e.message)
      setView('input')
    }
  }, [])

  return (
    <div className="min-h-screen">
      <header className="no-print border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-600 font-bold text-white">IL</span>
            <div>
              <h1 className="text-lg font-semibold leading-tight">InterviewLens</h1>
              <p className="text-xs text-slate-500">Fully-local interview-prep research</p>
            </div>
          </div>
          {health && (
            <HealthBadge health={health} />
          )}
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        {error && (
          <div className="no-print mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {view === 'input' && <InputPanel onSubmit={research} />}
        {view === 'progress' && <ProgressView events={events} />}
        {view === 'results' && result && (
          <ResultsView result={result} onNewSearch={() => setView('input')} onRerun={research} />
        )}
      </main>
    </div>
  )
}

function HealthBadge({ health }) {
  if (health.unreachable) {
    return <Badge color="red" label="backend unreachable" />
  }
  const ollamaOk = health.ollama?.reachable
  const modelsOk = ollamaOk && Object.values(health.ollama.models || {}).every((m) => m.present)
  const searxOk = health.searxng?.json_api
  if (ollamaOk && modelsOk && searxOk) return <Badge color="green" label="all systems ready" />
  if (!ollamaOk) return <Badge color="red" label="Ollama not running — see setup.md" />
  if (!modelsOk) return <Badge color="amber" label="models missing — run ollama pull" />
  return <Badge color="amber" label="search engine not ready" />
}

function Badge({ color, label }) {
  const colors = {
    green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    red: 'bg-red-50 text-red-700 border-red-200',
  }
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium ${colors[color]}`}>
      {label}
    </span>
  )
}
