"""
Pydantic-Modelle für Parser v2.0.
ParseResponse ist der Wrapper für den Ollama format-Parameter
(top-level muss type=object sein — Arrays werden nicht akzeptiert).
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Confidence(str, Enum):
    hoch    = "hoch"
    mittel  = "mittel"
    niedrig = "niedrig"


class Kategorie(str, Enum):
    stehplatz = "Stehplatz"
    sitzplatz = "Sitzplatz"
    vip       = "VIP"
    front     = "Front-of-Stage"
    gemischt  = "Gemischt"
    unbekannt = "Unbekannt"


class EventResult(BaseModel):
    event_name:              Optional[str]   = None
    event_datum:             Optional[str]   = None
    venue:                   Optional[str]   = None
    stadt:                   Optional[str]   = None
    kategorie:               Kategorie       = Kategorie.unbekannt
    anzahl_karten:           Optional[int]   = None
    angebotspreis_gesamt:    Optional[float] = None
    preis_ist_pro_karte:     Optional[bool]  = None
    originalpreis_pro_karte: Optional[float] = None
    confidence:              Confidence      = Confidence.niedrig
    confidence_grund:        Optional[str]   = None


class ParseResponse(BaseModel):
    events: list[EventResult]


# Ollama's format-Parameter erwartet type=object auf Top-Level.
# ParseResponse ist der Wrapper: {"events": [...]}
OLLAMA_FORMAT_SCHEMA: dict = ParseResponse.model_json_schema()
