from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Candidate, CandidateVector
from app.services.embedding_backend import get_embedding_backend


@dataclass
class VectorSearchHit:
    candidate_id: int
    similarity: float
    metadata: dict


class CandidateVectorStore:
    def __init__(self, db: Session):
        self.db = db
        self.backend = get_embedding_backend()

    @property
    def model_name(self) -> str:
        return self.backend.model_name

    def embed_text(self, text: str) -> list[float]:
        return self.backend.encode([text])[0]

    def upsert_candidate_vector(self, candidate: Candidate, vector_text: str, metadata: dict, vector_type: str = "profile") -> CandidateVector:
        embedding = self.embed_text(vector_text)
        source_hash = hashlib.sha256(vector_text.encode("utf-8")).hexdigest()
        row = self.db.scalar(
            select(CandidateVector).where(
                CandidateVector.candidate_id == candidate.id,
                CandidateVector.vector_type == vector_type,
            )
        )
        payload = {
            "embedding_model": self.model_name,
            "embedding_dim": len(embedding),
            "embedding_json": json.dumps(embedding),
            "source_text": vector_text,
            "source_hash": source_hash,
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
        }
        if row is None:
            row = CandidateVector(candidate_id=candidate.id, vector_type=vector_type, **payload)
            self.db.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        return row

    def candidate_hits(self, query_text: str, candidate_ids: list[int] | None = None, limit: int = 20) -> list[VectorSearchHit]:
        query_embedding = self.embed_text(query_text)
        stmt = select(CandidateVector)
        if candidate_ids:
            stmt = stmt.where(CandidateVector.candidate_id.in_(candidate_ids))
        rows = self.db.scalars(stmt).all()
        hits: list[VectorSearchHit] = []
        for row in rows:
            embedding = json.loads(row.embedding_json)
            similarity = cosine_similarity(query_embedding, embedding)
            hits.append(
                VectorSearchHit(
                    candidate_id=row.candidate_id,
                    similarity=similarity,
                    metadata=json.loads(row.metadata_json or "{}"),
                )
            )
        hits.sort(key=lambda item: item.similarity, reverse=True)
        return hits[:limit]



def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return dot / (left_norm * right_norm)
