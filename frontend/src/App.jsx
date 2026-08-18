import { useEffect, useRef, useState } from 'react'
import { fetchStats, uploadCsv, fetchJobStatus } from './api'

// Deux categories, chacune avec son identite visuelle.
const PANELS = [
  {
    key: 'normal',
    title: 'Comportements normaux',
    hint: 'Les allees et venues attendues sur un site.',
    accent: 'teal',
  },
  {
    key: 'suspect',
    title: 'Comportements suspects',
    hint: 'Les signaux qui precedent une intrusion.',
    accent: 'amber',
  },
]

export default function App() {
  const [stats, setStats] = useState(null)
  const [statsError, setStatsError] = useState(null)

  async function refreshStats() {
    try {
      const data = await fetchStats()
      if (data.ok === false) throw new Error(data.error || 'Erreur inconnue')
      setStats(data)
      setStatsError(null)
    } catch (e) {
      setStatsError(e.message)
    }
  }

  useEffect(() => {
    refreshStats()
  }, [])

  return (
    <div className="page">
      <Header stats={stats} error={statsError} />
      <main className="panels">
        {PANELS.map((p) => (
          <CategoryPanel key={p.key} config={p} onIndexed={refreshStats} />
        ))}
      </main>
      <footer className="foot">
        Previa · infrastructure de donnees comportementales pour Sentinel X
      </footer>
    </div>
  )
}

function Header({ stats, error }) {
  const total = stats?.total ?? 0
  const normal = stats?.normal ?? 0
  const suspect = stats?.suspect ?? 0
  const normalPct = total ? (normal / total) * 100 : 50
  const suspectPct = total ? (suspect / total) * 100 : 50

  return (
    <header className="header">
      <div className="brand">
        <span className="brand-mark">Previa</span>
        <p className="brand-sub">Indexation des comportements de reference</p>
      </div>

      <div className="gauge" role="status" aria-live="polite">
        <div className="gauge-number">{total}</div>
        <div className="gauge-label">comportements indexes</div>
        <div className="gauge-bar" aria-hidden="true">
          <span className="seg seg-teal" style={{ width: `${normalPct}%` }} />
          <span className="seg seg-amber" style={{ width: `${suspectPct}%` }} />
        </div>
        <div className="gauge-legend">
          <span><i className="dot dot-teal" />{normal} normaux</span>
          <span><i className="dot dot-amber" />{suspect} suspects</span>
        </div>
        {error && <div className="gauge-offline">Serveur injoignable</div>}
      </div>
    </header>
  )
}

function CategoryPanel({ config, onIndexed }) {
  const { key, title, hint, accent } = config
  const [files, setFiles] = useState([])
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  function addFiles(fileList) {
    const csvs = Array.from(fileList).filter((f) =>
      f.name.toLowerCase().endsWith('.csv'),
    )
    // Evite les doublons par nom.
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name))
      return [...prev, ...csvs.filter((f) => !names.has(f.name))]
    })
  }

  function removeFile(name) {
    setFiles((prev) => prev.filter((f) => f.name !== name))
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    addFiles(e.dataTransfer.files)
  }

  // Interroge la progression d'un job toutes les 2 secondes.
  async function pollJob(jobId, fileName, outcomeRef) {
    return new Promise((resolve) => {
      const interval = setInterval(async () => {
        try {
          const job = await fetchJobStatus(jobId)

          // Mettre a jour la progression en temps reel
          const progressMsg = job.total_batches > 0
            ? `Vectorisation : lot ${job.batches_done}/${job.total_batches}`
            : job.message || 'Traitement en cours...'

          const progressPct = job.total_batches > 0
            ? Math.round((job.batches_done / job.total_batches) * 100)
            : null

          // Mise a jour de l'affichage pendant le traitement
          setResults((prev) => {
            const updated = [...prev]
            const idx = updated.findIndex((r) => r.name === fileName && r.status === 'en cours')
            if (idx >= 0) {
              updated[idx] = {
                ...updated[idx],
                message: progressMsg,
                progress: progressPct,
              }
            }
            return updated
          })

          if (job.status === 'done') {
            clearInterval(interval)
            resolve({
              name: fileName,
              status: 'ok',
              message: job.message || `${job.result?.points_inseres} comportements indexes`,
            })
          } else if (job.status === 'error') {
            clearInterval(interval)
            resolve({
              name: fileName,
              status: 'erreur',
              message: job.message,
            })
          }
        } catch (e) {
          // Erreur reseau temporaire, on continue a poller
          console.warn('Erreur de polling:', e.message)
        }
      }, 2000)
    })
  }

  async function index() {
    if (!files.length || busy) return
    setBusy(true)
    const outcome = []
    for (const file of files) {
      setResults([...outcome, { name: file.name, status: 'en cours', message: 'Envoi du fichier...' }])
      try {
        const data = await uploadCsv(key, file)
        if (data.job_id) {
          // Import asynchrone : on poll la progression
          const result = await pollJob(data.job_id, file.name, outcome)
          outcome.push(result)
        } else {
          // Reponse directe (pas de job_id)
          outcome.push({
            name: file.name,
            status: 'ok',
            message: `${data.points_inseres} comportements indexes`,
          })
        }
      } catch (e) {
        outcome.push({ name: file.name, status: 'erreur', message: e.message })
      }
      setResults([...outcome])
    }
    setBusy(false)
    setFiles([])
    onIndexed()
  }

  return (
    <section className={`panel accent-${accent}`}>
      <div className="panel-head">
        <h2>{title}</h2>
        <p>{hint}</p>
      </div>

      <button
        type="button"
        className={`drop ${dragging ? 'drop-active' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <span className="drop-title">Deposer des fichiers CSV</span>
        <span className="drop-sub">ou cliquer pour parcourir</span>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          multiple
          hidden
          onChange={(e) => {
            addFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </button>

      {files.length > 0 && (
        <ul className="filelist">
          {files.map((f) => (
            <li key={f.name}>
              <span className="filename">{f.name}</span>
              <button
                type="button"
                className="remove"
                onClick={() => removeFile(f.name)}
                aria-label={`Retirer ${f.name}`}
              >
                x
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        className="index-btn"
        disabled={!files.length || busy}
        onClick={index}
      >
        {busy
          ? 'Indexation en cours…'
          : files.length
            ? `Indexer ${files.length} fichier${files.length > 1 ? 's' : ''}`
            : 'Indexer'}
      </button>

      {results.length > 0 && (
        <ul className="results">
          {results.map((r, i) => (
            <li key={i} className={`res res-${r.status === 'ok' ? 'ok' : r.status === 'erreur' ? 'err' : 'run'}`}>
              <div className="res-top">
                <span className="res-name">{r.name}</span>
                <span className="res-msg">{r.message || r.status}</span>
              </div>
              {r.status === 'en cours' && r.progress != null && (
                <div className="res-progress">
                  <div className="res-progress-bar" style={{ width: `${r.progress}%` }} />
                  <span className="res-progress-text">{r.progress}%</span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}