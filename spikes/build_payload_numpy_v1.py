import json
from pathlib import Path

from open_source_risk_model.service.score_repo import score_repo

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "examples" / "payload_numpy_v1.json"

def main() -> None:
    payload = score_repo("numpy/numpy", refresh=False, fetch_issues=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"Wrote payload: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
