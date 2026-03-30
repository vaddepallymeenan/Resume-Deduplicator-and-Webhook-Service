"""
Resume Deduplication System
============================
Detects duplicate resumes using a multi-stage pipeline:
  1. Candidate hashing (MinHash + LSH) for fast approximate matching
  2. TF-IDF + Cosine Similarity for section-level comparison
  3. Weighted scoring across key resume sections
"""

import re
import json
import hashlib
import pickle
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datasketch import MinHash, MinHashLSH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Resume:
    """Parsed representation of a resume."""
    resume_id: str
    raw_text: str
    name: str = ""
    email: str = ""
    phone: str = ""
    skills: str = ""
    experience: str = ""
    education: str = ""
    summary: str = ""

    # Derived
    normalized_text: str = field(default="", repr=False)
    minhash: Optional[object] = field(default=None, repr=False)

    def __post_init__(self):
        self.normalized_text = normalize_text(self.raw_text)


@dataclass
class DuplicateResult:
    query_id: str
    match_id: str
    similarity_score: float
    is_duplicate: bool
    method: str
    section_scores: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Lowercase, remove punctuation/extra whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_shingles(text: str, k: int = 3) -> set:
    """Character k-shingles for MinHash."""
    tokens = text.split()
    if len(tokens) < k:
        return set(tokens)
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def build_minhash(text: str, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for shingle in extract_shingles(text):
        m.update(shingle.encode("utf8"))
    return m


# ---------------------------------------------------------------------------
# Resume parser (simple regex-based; replace with LLM-based parser in prod)
# ---------------------------------------------------------------------------

SECTION_PATTERNS = {
    "skills":     re.compile(r"skills?[:\s]+(.*?)(?=\n[A-Z]|\Z)", re.I | re.S),
    "experience": re.compile(r"experience[:\s]+(.*?)(?=\n[A-Z]|\Z)", re.I | re.S),
    "education":  re.compile(r"education[:\s]+(.*?)(?=\n[A-Z]|\Z)", re.I | re.S),
    "summary":    re.compile(r"(?:summary|objective|profile)[:\s]+(.*?)(?=\n[A-Z]|\Z)", re.I | re.S),
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
PHONE_RE = re.compile(r"[\+\(]?[\d\s\-\(\)]{7,15}")


def parse_resume(resume_id: str, raw_text: str) -> Resume:
    """Extract structured fields from raw resume text."""
    sections = {k: "" for k in SECTION_PATTERNS}
    for key, pat in SECTION_PATTERNS.items():
        m = pat.search(raw_text)
        if m:
            sections[key] = normalize_text(m.group(1))

    emails = EMAIL_RE.findall(raw_text)
    phones = PHONE_RE.findall(raw_text)

    r = Resume(
        resume_id=resume_id,
        raw_text=raw_text,
        email=emails[0].lower() if emails else "",
        phone=re.sub(r"\s+", "", phones[0]) if phones else "",
        **sections,
    )
    r.minhash = build_minhash(r.normalized_text)
    return r


# ---------------------------------------------------------------------------
# Core deduplication engine
# ---------------------------------------------------------------------------

class ResumeDuplicateDetector:
    """
    Multi-stage duplicate detector:
      Stage 1 – Exact hash (email / phone)
      Stage 2 – LSH approximate match (fast, sub-linear)
      Stage 3 – TF-IDF cosine similarity (accurate)
    """

    # Weights per section for final score
    SECTION_WEIGHTS = {
        "skills":      0.35,
        "experience":  0.35,
        "education":   0.15,
        "summary":     0.15,
    }

    def __init__(
        self,
        threshold: float = 0.85,
        lsh_threshold: float = 0.5,
        num_perm: int = 128,
    ):
        self.threshold = threshold
        self.lsh_threshold = lsh_threshold
        self.num_perm = num_perm

        self._db: dict[str, Resume] = {}
        self._lsh = MinHashLSH(threshold=lsh_threshold, num_perm=num_perm)
        self._vectorizers: dict[str, TfidfVectorizer] = {}
        self._tfidf_matrices: dict[str, object] = {}  # section → sparse matrix
        self._id_order: list[str] = []  # keeps insertion order for matrix rows

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_resume(self, resume: Resume) -> None:
        """Index a resume into all data structures."""
        if resume.resume_id in self._db:
            log.warning("Resume %s already indexed – skipping.", resume.resume_id)
            return

        self._db[resume.resume_id] = resume
        self._lsh.insert(resume.resume_id, resume.minhash)
        self._id_order.append(resume.resume_id)
        self._invalidate_tfidf()

    def add_resumes_bulk(self, resumes: list[Resume]) -> None:
        for r in resumes:
            self.add_resume(r)
        self._rebuild_tfidf()

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def is_duplicate(self, query: Resume) -> DuplicateResult:
        """Full pipeline check against the indexed database."""

        # Stage 1: exact identifier match
        for rid, stored in self._db.items():
            if query.email and query.email == stored.email:
                return DuplicateResult(
                    query_id=query.resume_id,
                    match_id=rid,
                    similarity_score=1.0,
                    is_duplicate=True,
                    method="exact_email",
                )
            if query.phone and query.phone == stored.phone:
                return DuplicateResult(
                    query_id=query.resume_id,
                    match_id=rid,
                    similarity_score=1.0,
                    is_duplicate=True,
                    method="exact_phone",
                )

        # Stage 2: LSH candidates
        candidates = self._lsh.query(query.minhash)
        if not candidates:
            return DuplicateResult(
                query_id=query.resume_id,
                match_id="",
                similarity_score=0.0,
                is_duplicate=False,
                method="lsh_no_candidates",
            )

        # Stage 3: TF-IDF cosine over candidates
        best_id, best_score, best_sections = "", 0.0, {}
        for cid in candidates:
            score, section_scores = self._cosine_score(query, self._db[cid])
            if score > best_score:
                best_score = score
                best_id = cid
                best_sections = section_scores

        is_dup = best_score >= self.threshold
        return DuplicateResult(
            query_id=query.resume_id,
            match_id=best_id,
            similarity_score=round(best_score, 4),
            is_duplicate=is_dup,
            method="tfidf_cosine",
            section_scores=best_sections,
        )

    # ------------------------------------------------------------------
    # TF-IDF helpers
    # ------------------------------------------------------------------

    def _invalidate_tfidf(self) -> None:
        self._tfidf_matrices = {}
        self._vectorizers = {}

    def _rebuild_tfidf(self) -> None:
        """Fit a TF-IDF vectorizer per section over all indexed resumes."""
        self._tfidf_matrices = {}
        self._vectorizers = {}
        for section in self.SECTION_WEIGHTS:
            texts = [getattr(self._db[rid], section) or " " for rid in self._id_order]
            vect = TfidfVectorizer(min_df=1, ngram_range=(1, 2))
            mat = vect.fit_transform(texts)
            self._vectorizers[section] = vect
            self._tfidf_matrices[section] = mat

    def _cosine_score(
        self, query: Resume, stored: Resume
    ) -> tuple[float, dict]:
        """Weighted cosine similarity across resume sections."""
        if not self._vectorizers:
            self._rebuild_tfidf()

        total, section_scores = 0.0, {}
        for section, weight in self.SECTION_WEIGHTS.items():
            q_text = getattr(query, section) or " "
            s_text = getattr(stored, section) or " "
            vect = self._vectorizers.get(section)
            if vect is None:
                continue
            try:
                qv = vect.transform([q_text])
                sv = vect.transform([s_text])
                sim = float(cosine_similarity(qv, sv)[0][0])
            except Exception:
                sim = 0.0
            section_scores[section] = round(sim, 4)
            total += weight * sim

        return total, section_scores

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(self, f)
        log.info("Detector saved → %s", path)

    @classmethod
    def load(cls, path: str) -> "ResumeDuplicateDetector":
        with open(path, "rb") as f:
            obj = pickle.load(f)
        log.info("Detector loaded ← %s  (%d resumes)", path, len(obj._db))
        return obj

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        return {
            "indexed_resumes": len(self._db),
            "threshold": self.threshold,
            "lsh_threshold": self.lsh_threshold,
        }
