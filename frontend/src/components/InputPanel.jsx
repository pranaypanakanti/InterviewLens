import { useRef, useState } from 'react'

export default function InputPanel({ onSubmit }) {
  const [jdText, setJdText] = useState('')
  const [resumeFile, setResumeFile] = useState(null)
  const [mode, setMode] = useState('quality')
  const [dragOver, setDragOver] = useState(false)
  const fileInput = useRef(null)

  const canSubmit = jdText.trim().length >= 40 && resumeFile

  const pickFile = (file) => {
    if (!file) return
    const ok = /\.(pdf|docx|txt)$/i.test(file.name)
    if (!ok) {
      alert('Please upload a .pdf, .docx, or .txt resume.')
      return
    }
    setResumeFile(file)
  }

  return (
    <div>
      <div className="mb-8 text-center">
        <h2 className="text-2xl font-semibold">Research your interview</h2>
        <p className="mt-1 text-sm text-slate-500">
          Paste the job description and drop your resume. InterviewLens searches the web for the
          questions actually asked at that company, then writes answers tailored to you.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* JD panel */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <label className="mb-2 block text-sm font-medium text-slate-700">Job description</label>
          <textarea
            className="h-64 w-full resize-none rounded-lg border border-slate-200 p-3 text-sm focus:border-accent-500 focus:outline-none focus:ring-1 focus:ring-accent-500"
            placeholder="Paste the full job description here (company name included helps a lot)…"
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
          />
          <p className="mt-1 text-xs text-slate-400">{jdText.trim().length} characters</p>
        </div>

        {/* Resume panel */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <label className="mb-2 block text-sm font-medium text-slate-700">Resume</label>
          <div
            className={`flex h-64 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center transition ${
              dragOver ? 'border-accent-500 bg-accent-50' : 'border-slate-300 hover:border-accent-500'
            }`}
            onClick={() => fileInput.current.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              pickFile(e.dataTransfer.files[0])
            }}
          >
            {resumeFile ? (
              <>
                <div className="text-3xl">📄</div>
                <p className="mt-2 text-sm font-medium text-slate-700">{resumeFile.name}</p>
                <p className="mt-1 text-xs text-slate-400">
                  {(resumeFile.size / 1024).toFixed(0)} KB — click to replace
                </p>
              </>
            ) : (
              <>
                <div className="text-3xl">⬆️</div>
                <p className="mt-2 text-sm text-slate-600">
                  Drag &amp; drop your resume here, or click to browse
                </p>
                <p className="mt-1 text-xs text-slate-400">.pdf, .docx or .txt</p>
              </>
            )}
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.docx,.txt"
              className="hidden"
              onChange={(e) => pickFile(e.target.files[0])}
            />
          </div>
        </div>
      </div>

      {/* Mode toggle + submit */}
      <div className="mt-6 flex flex-col items-center gap-4">
        <div className="flex items-center gap-1 rounded-full border border-slate-200 bg-white p-1 shadow-sm">
          {[
            ['fast', 'Fast (3B)'],
            ['quality', 'Quality (7B)'],
          ].map(([value, label]) => (
            <button
              key={value}
              onClick={() => setMode(value)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                mode === value ? 'bg-accent-600 text-white' : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="text-xs text-slate-400">
          Fast answers in minutes; Quality uses the 7B model (slower on 4 GB VRAM, better answers).
        </p>
        <button
          disabled={!canSubmit}
          onClick={() => onSubmit({ jdText, resumeFile, mode, force: false })}
          className="rounded-xl bg-accent-600 px-10 py-3 text-base font-semibold text-white shadow-sm transition hover:bg-accent-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Research →
        </button>
      </div>
    </div>
  )
}
