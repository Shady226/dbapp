// Adresse du backend FastAPI. Modifiable via un fichier .env (VITE_API_URL).
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Recupere le decompte des comportements indexes (total / normal / suspect).
export async function fetchStats() {
  const res = await fetch(`${BASE}/stats`)
  if (!res.ok) throw new Error(`Le serveur a repondu ${res.status}`)
  return res.json()
}

// Envoie un fichier CSV avec sa categorie au backend.
// Retourne immediatement avec un job_id.
export async function uploadCsv(category, file) {
  const form = new FormData()
  form.append('category', category)
  form.append('file', file)

  const res = await fetch(`${BASE}/upload`, {
    method: 'POST',
    body: form,
  })

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    // FastAPI renvoie le motif dans le champ "detail".
    throw new Error(data.detail || `Le serveur a repondu ${res.status}`)
  }
  return data
}

// Interroge l'etat d'un job d'import.
export async function fetchJobStatus(jobId) {
  const res = await fetch(`${BASE}/job/${jobId}`)
  if (!res.ok) throw new Error(`Le serveur a repondu ${res.status}`)
  return res.json()
}