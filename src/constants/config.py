"""Configuration-related constants and paths.

This module contains all the file paths and configuration-related constants
used throughout the application.
"""

import os
from pathlib import Path

# Project directory structure
# `PROJECT_ROOT` should point to the repository root (one level above `src/`).
# Use `resolve().parents[2]` to reliably get the workspace root regardless of
# how the module is imported or the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Data directories
DATA_DIR = PROJECT_ROOT / "data"

# State files
STATE_PATH = DATA_DIR / "splitwise_exported.json"


# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
