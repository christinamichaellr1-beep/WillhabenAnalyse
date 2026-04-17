"""Shared pytest fixtures for parser/v2 tests."""
import sys
from pathlib import Path

# Project root on sys.path so imports work without installation
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
