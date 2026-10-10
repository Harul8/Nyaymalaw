"""Final isolated planner comparison; same four cases, separate evidence."""
import importlib.util
from pathlib import Path


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("research_probe_base", folder / "research-probe.py")
    evaluation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluation)
    evaluation.EVIDENCE = folder / "research-probe-revised.json"
    evaluation.main()
