# Previa

Application web d'ingestion de comportements (normaux / suspects) vers Qdrant,
avec recherche par similarite et integration d'un modele d'IA.

## Architecture

- **backend/** : API FastAPI (Python). Upload CSV -> embeddings Gemini -> Qdrant.
- **frontend/** : interface React (a venir, etape 4).
- **Qdrant Cloud** : base vectorielle managee.
- **Gemini** : modele d'embedding `gemini-embedding-001` (768 dimensions).

## Etape 1 : mise en place et test de connexion

### 1. Installer les dependances

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurer les secrets

```bash
cp .env.example .env
```

Puis edite `.env` et colle :
- `QDRANT_URL` et `QDRANT_API_KEY` (depuis cloud.qdrant.io)
- `GEMINI_API_KEY` (depuis aistudio.google.com)

### 3. Lancer l'API

```bash
uvicorn app.main:app --reload
```

### 4. Verifier

Ouvre http://localhost:8000/health dans le navigateur.
Reponse attendue si tout est bon :

```json
{
  "ok": true,
  "qdrant": { "connected": true, "collections": [] },
  "gemini": { "connected": true, "dimension": 768 }
}
```

Documentation interactive de l'API : http://localhost:8000/docs
