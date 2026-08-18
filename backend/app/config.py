"""Chargement centralise de la configuration depuis le fichier .env."""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    QDRANT_URL: str = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "previa_comportements")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "768"))

    # Origines autorisees a appeler l'API (CORS), separees par des virgules.
    # En prod, positionner ALLOWED_ORIGINS avec l'URL du frontend deploye.
    ALLOWED_ORIGINS: list[str] = [
        o.strip() for o in os.getenv(
            "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
        ).split(",") if o.strip()
    ]

    def check(self) -> list[str]:
        """Retourne la liste des variables manquantes."""
        missing = []
        for name in ("QDRANT_URL", "QDRANT_API_KEY", "GEMINI_API_KEY"):
            if not getattr(self, name):
                missing.append(name)
        return missing


settings = Settings()
