"""Point d'entree de l'API FastAPI - Import asynchrone avec suivi de progression."""
import uuid
import threading
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from . import qdrant, ingest
from .embeddings import embed_text, embed_texts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Categories autorisees a l'upload.
CATEGORIES = {"normal", "suspect"}

# Stockage en memoire des jobs d'import en cours / termines.
_jobs: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Au demarrage : s'assure que la collection Qdrant existe."""
    try:
        qdrant.ensure_collection()
    except Exception as e:
        # On ne bloque pas le demarrage ; l'erreur reapparaitra clairement
        # lors d'un upload si la connexion Qdrant est reellement en panne.
        print(f"[startup] Impossible de preparer la collection : {e}")
    yield


app = FastAPI(title="Previa API", version="0.3.0", lifespan=lifespan)

# Autorise le frontend (local + deploye, via ALLOWED_ORIGINS) a appeler l'API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"service": "Previa API", "status": "ok"}


@app.get("/health")
def health():
    """Verifie la config, la connexion Qdrant et l'API Gemini."""
    missing = settings.check()
    if missing:
        return {"ok": False, "error": f"Variables manquantes: {missing}"}

    report = {"ok": True}
    try:
        report["qdrant"] = qdrant.ping()
    except Exception as e:
        report["ok"] = False
        report["qdrant"] = {"connected": False, "error": str(e)}
    try:
        vec = embed_text("test de connexion")
        report["gemini"] = {"connected": True, "dimension": len(vec)}
    except Exception as e:
        report["ok"] = False
        report["gemini"] = {"connected": False, "error": str(e)}
    return report


@app.get("/stats")
def get_stats():
    """Decompte des comportements indexes (total, normaux, suspects)."""
    try:
        return {"ok": True, **qdrant.stats()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _run_import(job_id: str, records: list[dict], category: str, filename: str):
    """Fonction executee dans un thread pour l'import long."""
    job = _jobs[job_id]
    total = len(records)
    try:
        # Vectorisation avec callback de progression
        def on_progress(batch_done, total_batches):
            job["batches_done"] = batch_done
            job["total_batches"] = total_batches
            job["message"] = f"Vectorisation : lot {batch_done}/{total_batches}"

        job["message"] = "Vectorisation en cours..."
        vectors = embed_texts([r["text"] for r in records], progress_callback=on_progress)

        # Insertion dans Qdrant
        job["message"] = "Insertion dans Qdrant..."
        qdrant.ensure_collection()
        inserted = qdrant.upsert_points(records, vectors)

        job["status"] = "done"
        job["message"] = f"{inserted} comportements indexes avec succes"
        job["result"] = {
            "ok": True,
            "fichier": filename,
            "categorie": category,
            "lignes_traitees": total,
            "points_inseres": inserted,
            "total_dans_collection": qdrant.count_points(),
        }
        logger.info(f"[job {job_id}] Import termine : {inserted} points inseres.")

    except Exception as e:
        job["status"] = "error"
        job["message"] = str(e)
        job["result"] = {"ok": False, "error": str(e)}
        logger.error(f"[job {job_id}] Erreur : {e}")


@app.post("/upload")
async def upload_csv(
    category: str = Form(...),
    file: UploadFile = File(...),
):
    """Recoit un CSV + sa categorie, lance l'import en arriere-plan.

    Retourne immediatement un job_id pour suivre la progression.
    """
    # 1. Validation de la categorie
    if category not in CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Categorie invalide '{category}'. Attendu : {sorted(CATEGORIES)}",
        )

    # 2. Validation basique du fichier
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Le fichier doit etre un .csv")

    # 3. Lecture + parsing + validation des colonnes
    content = await file.read()
    try:
        records = ingest.parse_csv(content, category)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV illisible : {e}")

    if not records:
        raise HTTPException(status_code=422, detail="Le CSV ne contient aucune ligne.")

    # 4. Creer un job et lancer le traitement en arriere-plan
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "status": "running",
        "message": "Demarrage de l'import...",
        "filename": file.filename,
        "category": category,
        "total_records": len(records),
        "batches_done": 0,
        "total_batches": 0,
        "result": None,
    }

    thread = threading.Thread(
        target=_run_import,
        args=(job_id, records, category, file.filename),
        daemon=True,
    )
    thread.start()
    logger.info(f"[job {job_id}] Import lance : {len(records)} lignes de {file.filename}")

    return {
        "ok": True,
        "job_id": job_id,
        "message": f"Import lance pour {len(records)} lignes. Suivez la progression avec /job/{job_id}",
        "total_records": len(records),
    }


@app.get("/job/{job_id}")
def get_job_status(job_id: str):
    """Retourne l'etat d'un job d'import."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' introuvable")
    return _jobs[job_id]