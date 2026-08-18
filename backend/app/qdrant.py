"""Connexion au cluster Qdrant Cloud et operations sur la collection."""
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, PayloadSchemaType,
)

from .config import settings

client = QdrantClient(
    url=settings.QDRANT_URL,
    api_key=settings.QDRANT_API_KEY,
)

# Champ de payload sur lequel on filtre/compte -> necessite un index Qdrant.
_INDEXED_FIELD = "categorie_import"


def ping() -> dict:
    """Verifie que le cluster repond et liste les collections existantes."""
    collections = client.get_collections().collections
    return {
        "connected": True,
        "collections": [c.name for c in collections],
    }


def ensure_collection() -> None:
    """Cree la collection et l'index de payload si besoin.

    - La collection : vecteurs 768, distance cosinus.
    - L'index sur `categorie_import` : indispensable pour compter/filtrer
      par categorie sur Qdrant Cloud. La creation est idempotente.
    """
    existing = [c.name for c in client.get_collections().collections]
    if settings.QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=settings.EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
        )

    # Cree l'index sur le champ de categorie (sans erreur s'il existe deja).
    try:
        client.create_payload_index(
            collection_name=settings.QDRANT_COLLECTION,
            field_name=_INDEXED_FIELD,
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass  # index deja present : rien a faire


def upsert_points(records: list[dict], vectors: list[list[float]]) -> int:
    """Insere (ou met a jour) les points dans la collection.

    records : liste de dicts {id, text, payload}
    vectors : embeddings dans le meme ordre que records
    Retourne le nombre de points inseres.
    """
    points = [
        PointStruct(id=rec["id"], vector=vec, payload=rec["payload"])
        for rec, vec in zip(records, vectors)
    ]
    client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
    return len(points)


def count_points(category: str | None = None) -> int:
    """Compte les points, eventuellement filtres par categorie d'import."""
    count_filter = None
    if category is not None:
        count_filter = Filter(must=[
            FieldCondition(
                key=_INDEXED_FIELD,
                match=MatchValue(value=category),
            )
        ])
    return client.count(
        collection_name=settings.QDRANT_COLLECTION,
        count_filter=count_filter,
    ).count


def stats() -> dict:
    """Retourne le decompte total et par categorie."""
    ensure_collection()
    return {
        "total": count_points(),
        "normal": count_points("normal"),
        "suspect": count_points("suspect"),
    }
