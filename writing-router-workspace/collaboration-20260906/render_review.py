from pathlib import Path
import importlib.util
import json
import sys

root = Path(__file__).resolve().parent
path = Path(r"C:\Users\SanAn\.codex\skills\skill-creator\eval-viewer\generate_review.py")
spec = importlib.util.spec_from_file_location("skill_review", path)
review = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = review
spec.loader.exec_module(review)
runs = review.find_runs(root / "iteration-1")
runs.sort(key=lambda run: (run.get("eval_id", 0), "with_skill" not in run["id"]))
benchmark = json.loads((root / "benchmark.json").read_text(encoding="utf-8"))
html = review.generate_html(runs, "writing-router", None, benchmark)
(root / "review.html").write_text(html, encoding="utf-8")
print(json.dumps({"runs": len(runs), "html_bytes": len(html.encode("utf-8"))}))
