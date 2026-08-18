"""Generation d'embeddings via l'API Gemini (gemini-embedding-001).

Envoie les textes UN PAR UN pour eviter que batchEmbedContents
ne multiplie la consommation de quota. Chaque appel = 1 requete.
Avec 1.2s de delai entre chaque appel => ~50 req/min (< 100 limite).
500 textes => ~10 minutes.
"""
import math
import time
import logging
import re
from google import genai
from google.genai import types

from .config import settings

logger = logging.getLogger(__name__)

_client = genai.Client(api_key=settings.GEMINI_API_KEY)

_TASK_TYPE = "SEMANTIC_SIMILARITY"

# Delai entre chaque appel embed_content (1 texte a la fois)
_DELAY_BETWEEN_CALLS = 1.2  # secondes => ~50 req/min

# Retry patient
_MAX_RETRIES = 10
_BASE_RETRY_DELAY = 65.0  # 429 / quota depasse : Gemini demande d'attendre longtemps
_OVERLOAD_RETRY_DELAY = 15.0  # 503 / service temporairement surcharge : plus court


def _normalize(vector: list[float]) -> list[float]:
    """Normalise un vecteur (norme L2 = 1)."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


def _extract_retry_delay(error_str: str) -> float | None:
    """Extrait le delai de retry suggere par l'API Gemini."""
    try:
        match = re.search(r"retry\s+in\s+([\d.]+)", error_str.lower())
        if match:
            return float(match.group(1))
    except (ValueError, AttributeError):
        pass
    return None


def _embed_one_with_retry(text: str, label: str = "") -> list[float]:
    """Appelle embed_content pour UN SEUL texte avec retry patient."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = _client.models.embed_content(
                model=settings.EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type=_TASK_TYPE,
                    output_dimensionality=settings.EMBEDDING_DIM,
                ),
            )
            return _normalize(result.embeddings[0].values)

        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str
            is_overloaded = "503" in error_str or "UNAVAILABLE" in error_str
            if not is_rate_limit and not is_overloaded:
                raise

            if is_rate_limit:
                api_delay = _extract_retry_delay(error_str)
                wait = (api_delay + 10.0) if api_delay else _BASE_RETRY_DELAY
                reason = "Rate limit"
            else:
                wait = _OVERLOAD_RETRY_DELAY
                reason = "Service Gemini surcharge (503)"

            if attempt < _MAX_RETRIES:
                logger.warning(
                    f"{label} {reason} (tentative {attempt}/{_MAX_RETRIES}). "
                    f"Pause de {wait:.0f}s..."
                )
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"{reason} Gemini : {_MAX_RETRIES} tentatives echouees. "
                    f"Reessayez dans quelques minutes."
                ) from e

    raise RuntimeError("Echec inattendu.")


def embed_text(text: str) -> list[float]:
    """Transforme un seul texte en un vecteur de dimension EMBEDDING_DIM."""
    return _embed_one_with_retry(text)


def embed_texts(
    texts: list[str],
    progress_callback=None,
) -> list[list[float]]:
    """Transforme une liste de textes en vecteurs, un par un.

    Chaque texte = 1 appel API = 1 requete quota.
    Avec 1.2s de delai => ~50 req/min, bien sous le seuil de 100.
    500 textes => ~10 minutes.

    progress_callback: optionnel, callable(done, total) pour le suivi.
    """
    total = len(texts)
    estimated_min = total * _DELAY_BETWEEN_CALLS / 60
    vectors: list[float] = []

    logger.info(
        f"Debut embedding : {total} textes, un par un. "
        f"Duree estimee : ~{estimated_min:.0f} min."
    )

    for i, text in enumerate(texts):
        label = f"[{i + 1}/{total}]"

        vec = _embed_one_with_retry(text, label)
        vectors.append(vec)

        # Callback de progression (pour le frontend)
        if progress_callback:
            progress_callback(i + 1, total)

        # Log tous les 25 textes
        if (i + 1) % 25 == 0:
            pct = 100 * (i + 1) / total
            logger.info(f"Progression : {i + 1}/{total} ({pct:.0f}%)")

        # Pause entre chaque appel
        if i < total - 1:
            time.sleep(_DELAY_BETWEEN_CALLS)

    logger.info(f"Embedding termine : {len(vectors)} vecteurs generes.")
    return vectors