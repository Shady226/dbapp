"""Lecture et validation des CSV, construction des points Qdrant."""
import io
import uuid
import pandas as pd

# Colonnes attendues dans chaque fichier CSV.
EXPECTED_COLUMNS = [
    "id", "label", "type_site", "zone", "periode", "comportement",
    "indices_observables", "phase", "categorie", "niveau_risque",
    "niveau_alerte", "cas_limite", "justification",
]

# Champs texte concatenes pour produire l'embedding.
TEXT_FIELDS = ["comportement", "indices_observables", "justification"]

# Espace de noms fixe pour generer des UUID deterministes a partir de l'id.
_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-000000000042")


def make_point_id(original_id: str) -> str:
    """UUID deterministe : le meme id d'origine donne toujours le meme UUID.

    Cela permet a une reimportation d'ecraser (upsert) au lieu de dupliquer.
    """
    return str(uuid.uuid5(_NAMESPACE, str(original_id)))


def build_embedding_text(row: pd.Series) -> str:
    """Concatene les champs texte d'une ligne en un seul bloc a vectoriser."""
    parts = [str(row[f]).strip() for f in TEXT_FIELDS]
    return "\n".join(parts)


def parse_csv(file_bytes: bytes, category: str) -> list[dict]:
    """Lit un CSV et retourne une liste de dicts prets a etre inseres.

    Chaque dict contient : id (UUID), text (a vectoriser), payload (metadonnees).
    Leve une ValueError si des colonnes attendues manquent.
    """
    df = pd.read_csv(io.BytesIO(file_bytes))

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes dans le CSV : {missing}")

    records = []
    for _, row in df.iterrows():
        original_id = str(row["id"]).strip()
        payload = {col: _clean(row[col]) for col in EXPECTED_COLUMNS}
        # La categorie choisie a l'upload est stockee explicitement.
        payload["categorie_import"] = category
        records.append({
            "id": make_point_id(original_id),
            "text": build_embedding_text(row),
            "payload": payload,
        })
    return records


def _clean(value):
    """Convertit les types pandas/numpy en types Python natifs pour Qdrant."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):  # numpy int64/float64 -> int/float
        return value.item()
    return str(value).strip() if isinstance(value, str) else value
