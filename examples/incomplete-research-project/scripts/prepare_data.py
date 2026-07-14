"""Prototype only: the real split policy has not been approved."""

from pathlib import Path


def candidate_inputs() -> list[Path]:
    return [Path("data/raw/sample.csv")]
