export async function startAnalysis({ jdText, jobRole, resumeFile, mode, force }) {
  const form = new FormData()
  form.append('jd_text', jdText)
  form.append('job_role', jobRole)
  form.append('resume_file', resumeFile)
  form.append('mode', mode)
  form.append('force', force ? 'true' : 'false')
  const resp = await fetch('/api/analyze', { method: 'POST', body: form })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${resp.status})`)
  }
  return (await resp.json()).job_id
}

export function subscribeToJob(jobId, onEvent, onError) {
  const es = new EventSource(`/api/jobs/${jobId}/events`)
  es.onmessage = (e) => onEvent(JSON.parse(e.data))
  es.onerror = () => {
    es.close()
    onError && onError()
  }
  return es
}

export async function fetchResult(jobId) {
  const resp = await fetch(`/api/jobs/${jobId}/result`)
  if (!resp.ok) throw new Error(`Could not fetch result (${resp.status})`)
  return resp.json()
}

export async function fetchHealth() {
  const resp = await fetch('/api/health')
  if (!resp.ok) throw new Error('health check failed')
  return resp.json()
}
