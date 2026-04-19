"""Wikidata SPARQL client for event/artist lookup."""
from __future__ import annotations
import datetime
import logging
import requests

from .base import BaseClient, EventCandidate

logger = logging.getLogger(__name__)

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

SPARQL_QUERY = """
SELECT ?item ?itemLabel ?dateLabel WHERE {{
  ?item wdt:P31/wdt:P279* wd:Q2830826 .  # instance of concert or subclass
  ?item rdfs:label ?itemLabel .
  FILTER(LANG(?itemLabel) = "de" || LANG(?itemLabel) = "en")
  FILTER(CONTAINS(LCASE(?itemLabel), LCASE("{name}")))
  OPTIONAL {{ ?item wdt:P585 ?date . BIND(STR(?date) AS ?dateLabel) }}
}}
LIMIT 5
"""

class WikidataClient(BaseClient):
    SOURCE_NAME = "wikidata"

    def search(self, event_name: str, event_datum: datetime.date | None = None, stadt: str | None = None) -> list[EventCandidate]:
        query = SPARQL_QUERY.format(name=event_name.replace('"', ''))
        try:
            resp = requests.get(
                SPARQL_ENDPOINT,
                params={"query": query, "format": "json"},
                headers={"Accept": "application/json", "User-Agent": "WillhabenVerifier/1.0"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("WikidataClient.search fehlgeschlagen: %s", exc)
            return []

        candidates = []
        for binding in data.get("results", {}).get("bindings", []):
            name = binding.get("itemLabel", {}).get("value", "")
            date_str = binding.get("dateLabel", {}).get("value", "")
            date = None
            if date_str:
                try:
                    date = datetime.date.fromisoformat(date_str[:10])
                except ValueError:
                    pass
            candidates.append(EventCandidate(
                event_name=name,
                event_datum=date,
                source=self.SOURCE_NAME,
                confidence_score=0.6,
                raw=binding,
            ))
        return candidates
