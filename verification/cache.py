"""SQLite-backed cache for VerificationResult objects."""
from __future__ import annotations
import datetime
import json
import logging
import sqlite3
from pathlib import Path

from verification.orchestrator import VerifStatus, VerificationResult
from verification.matcher import MatchResult
from verification.clients.base import EventCandidate

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/verification_cache.db")
DEFAULT_TTL_DAYS = 7


def _normalize_key(event_name: str) -> str:
    return event_name.lower().strip()


def _result_to_dict(result: VerificationResult) -> dict:
    """Serialize VerificationResult to JSON-serializable dict."""
    best = None
    if result.best_match:
        bm = result.best_match
        cand = bm.candidate
        best = {
            "candidate": {
                "event_name": cand.event_name,
                "event_datum": cand.event_datum.isoformat() if cand.event_datum else None,
                "venue": cand.venue,
                "stadt": cand.stadt,
                "source": cand.source,
                "confidence_score": cand.confidence_score,
            },
            "name_score": bm.name_score,
            "date_score": bm.date_score,
            "city_score": bm.city_score,
            "total_score": bm.total_score,
        }
    return {
        "status": result.status.value,
        "best_match": best,
        "sources_checked": result.sources_checked,
        "sources_confirmed": result.sources_confirmed,
        "verif_datum": result.verif_datum,
        "notes": result.notes,
    }


def _dict_to_result(d: dict) -> VerificationResult:
    """Deserialize dict back to VerificationResult."""
    best_match = None
    bm_dict = d.get("best_match")
    if bm_dict:
        cand_dict = bm_dict["candidate"]
        datum = None
        if cand_dict.get("event_datum"):
            try:
                datum = datetime.date.fromisoformat(cand_dict["event_datum"])
            except ValueError:
                pass
        cand = EventCandidate(
            event_name=cand_dict["event_name"],
            event_datum=datum,
            venue=cand_dict.get("venue"),
            stadt=cand_dict.get("stadt"),
            source=cand_dict.get("source", ""),
            confidence_score=cand_dict.get("confidence_score", 0.0),
        )
        best_match = MatchResult(
            candidate=cand,
            name_score=bm_dict["name_score"],
            date_score=bm_dict["date_score"],
            city_score=bm_dict["city_score"],
            total_score=bm_dict["total_score"],
        )
    return VerificationResult(
        status=VerifStatus(d["status"]),
        best_match=best_match,
        sources_checked=d.get("sources_checked", []),
        sources_confirmed=d.get("sources_confirmed", []),
        verif_datum=d.get("verif_datum", ""),
        notes=d.get("notes", ""),
    )


class VerificationCache:
    """SQLite-backed verification cache with TTL."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH, ttl_days: int = DEFAULT_TTL_DAYS):
        self.db_path = db_path
        self.ttl_days = ttl_days
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS verif_cache (
                    event_name_key TEXT NOT NULL,
                    event_datum    TEXT NOT NULL DEFAULT '',
                    result_json    TEXT NOT NULL,
                    cached_at      TEXT NOT NULL,
                    PRIMARY KEY (event_name_key, event_datum)
                )
            """)

    def get(self, event_name: str, event_datum: datetime.date | None = None) -> VerificationResult | None:
        """Return cached result if not expired, else None."""
        key = _normalize_key(event_name)
        datum_str = event_datum.isoformat() if event_datum else ""
        cutoff = (datetime.date.today() - datetime.timedelta(days=self.ttl_days)).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT result_json, cached_at FROM verif_cache WHERE event_name_key=? AND event_datum=?",
                (key, datum_str),
            ).fetchone()
        if row is None:
            return None
        result_json, cached_at = row
        if cached_at < cutoff:
            logger.debug("Cache-Eintrag abgelaufen: %s %s", key, datum_str)
            return None
        try:
            return _dict_to_result(json.loads(result_json))
        except Exception as exc:
            logger.warning("Cache-Deserialisierung fehlgeschlagen: %s", exc)
            return None

    def put(self, event_name: str, event_datum: datetime.date | None, result: VerificationResult) -> None:
        """Store result in cache."""
        key = _normalize_key(event_name)
        datum_str = event_datum.isoformat() if event_datum else ""
        today = datetime.date.today().isoformat()
        data = json.dumps(_result_to_dict(result), ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO verif_cache (event_name_key, event_datum, result_json, cached_at) VALUES (?,?,?,?)",
                (key, datum_str, data, today),
            )

    def invalidate(self, event_name: str, event_datum: datetime.date | None = None) -> None:
        """Remove a specific entry from cache."""
        key = _normalize_key(event_name)
        datum_str = event_datum.isoformat() if event_datum else ""
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM verif_cache WHERE event_name_key=? AND event_datum=?",
                (key, datum_str),
            )

    def purge_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        cutoff = (datetime.date.today() - datetime.timedelta(days=self.ttl_days)).isoformat()
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM verif_cache WHERE cached_at < ?", (cutoff,))
            return cur.rowcount
