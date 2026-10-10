"""Repeat the same predeclared probes after the general prompt revision."""
from pathlib import Path

import evaluate_understanding_five as evaluation


if __name__ == "__main__":
    evaluation.EVIDENCE = Path(__file__).resolve().parent / "understanding-five-revised-live.json"
    evaluation.main()
