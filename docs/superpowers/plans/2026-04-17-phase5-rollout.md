# Phase 5 Rollout — Non-Ticket-Fix + Default-Switch

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Non-Ticket-False-Positives eliminieren (2/25 Eval-Fehler) und Parser v2 als Default aktivieren.

**Architecture:** `is_non_ticket_ad()` in preprocessing.py filtert Anzeigen ohne Event-Keywords vor dem LLM-Aufruf. Pipeline gibt `[]` zurück statt Fallback-Event.

**Tech Stack:** Python 3.12, Pydantic v2, Pytest, Ollama gemma3:27b

---

### Task 1: preprocessing.py — is_non_ticket_ad()

**Files:** Modify: `parser/v2/preprocessing.py`

- [ ] Add `_SIMILAR_ADS_MARKER`, `_EVENT_KEYWORDS`, `_extract_main_description()`, `is_non_ticket_ad()` — see impl below
- [ ] Run existing tests: `cd [worktree] && .venv/bin/pytest tests/test_v2_preprocessing.py -v` → all green

### Task 2: pipeline.py — return [] für filtered ads

**Files:** Modify: `parser/v2/pipeline.py`, `tests/test_v2_pipeline.py`

- [ ] Change category-page branch to `return []`
- [ ] Add `is_non_ticket_ad` check → `return []`
- [ ] Update `test_parse_ad_category_page_skipped_without_ollama_call` → expects `result == []`
- [ ] Add `test_parse_ad_non_ticket_returns_empty_list`

### Task 3: main.py — default v2

**Files:** Modify: `main.py`

- [ ] `run_pipeline(parser_version: str = "v2")`
- [ ] `--parser-version default="v2"`, help text aktualisieren

### Task 4: README.md

**Files:** Create: `README.md`

- [ ] v2.0 Feature-Übersicht, Eval-Ergebnisse, CLI-Params, Rollback-Anleitung, Eval-Suite

### Task 5: Git Commit

- [ ] `git add -A && git commit -m "feat(parser): v2.0 ..."`
