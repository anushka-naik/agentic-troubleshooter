"""Compare the agentic workflow with a RAG-only baseline on data/scenarios.json.

    python -m eval.run_eval                 # all scenarios, both systems
    python -m eval.run_eval --cases none-sort json-empty
    python -m eval.run_eval --skip-baseline

Metrics per case:
  root_cause_hit      every keyword group in `expected.root_cause_keywords` appears
                      in the root cause or reasoning (each group is an any-of list)
  error_type_correct  agentic only; the baseline does not classify errors
  verification_ok     a fix was verified in the sandbox iff the case is expected to
                      be verifiable (so a "verified" environment fix counts as wrong)
  grounded_fixes      share of fixes whose citations all exist and are non-empty
  latency_s, llm_calls

Both systems' fixes are checked by the same validator, so the comparison
isolates the workflow, not the checking.
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from troubleshooter.agents.validator import Validator
from troubleshooter.baseline import run_baseline
from troubleshooter.config import get_settings
from troubleshooter.llm import StructuredLLM
from troubleshooter.schemas import TroubleshootRequest
from troubleshooter.service import TroubleshootService

RESULTS_DIR = Path(__file__).parent / "results"


def keyword_hit(text: str, groups: list[list[str]]) -> bool:
    text = text.lower()
    return all(any(keyword in text for keyword in group) for group in groups)


def evaluate_agentic(service: TroubleshootService, case: dict) -> dict:
    expected = case["expected"]
    started = time.perf_counter()
    report = service.run(TroubleshootRequest(query=case["query"], code=case["code"], enable_github=False))
    verified = any(fix.validation.status == "verified" for fix in report.fixes)
    return {
        "root_cause_hit": keyword_hit(f"{report.root_cause} {report.reasoning}", expected["root_cause_keywords"]),
        "error_type_correct": (report.error_type or None) == expected["error_type"],
        "verification_ok": verified == expected["verifiable"],
        "grounded_fixes": _share(fix.validation.grounded for fix in report.fixes),
        "statuses": [fix.validation.status for fix in report.fixes],
        "revisions": report.revisions,
        "llm_calls": report.llm_calls,
        "latency_s": round(time.perf_counter() - started, 2),
    }


def evaluate_baseline(service: TroubleshootService, validator: Validator, case: dict) -> dict:
    expected = case["expected"]
    request = TroubleshootRequest(query=case["query"], code=case["code"])
    started = time.perf_counter()
    diagnosis, evidence = run_baseline(service.llm, service.retriever, request)
    latency = time.perf_counter() - started

    evidence_ids = {item.id for item in evidence}
    validations = [
        validator.validate_fix(i, fix, case["code"], evidence_ids, None) for i, fix in enumerate(diagnosis.fixes)
    ]
    verified = any(v.status == "verified" for v in validations)
    return {
        "root_cause_hit": keyword_hit(f"{diagnosis.root_cause} {diagnosis.reasoning}", expected["root_cause_keywords"]),
        "error_type_correct": None,
        "verification_ok": verified == expected["verifiable"],
        "grounded_fixes": _share(v.grounded for v in validations),
        "statuses": [v.status for v in validations],
        "revisions": 0,
        "llm_calls": 1,
        "latency_s": round(latency, 2),
    }


def _share(flags) -> float:
    flags = list(flags)
    return round(sum(flags) / len(flags), 2) if flags else 0.0


def summarise(rows: list[dict]) -> dict:
    def mean(key):
        values = [row[key] for row in rows if row[key] is not None]
        return round(sum(values) / len(values), 2) if values else None

    return {
        key: mean(key)
        for key in (
            "root_cause_hit",
            "error_type_correct",
            "verification_ok",
            "grounded_fixes",
            "llm_calls",
            "latency_s",
        )
    }


def print_table(results: dict) -> None:
    systems = list(results["summary"])
    metrics = ["root_cause_hit", "error_type_correct", "verification_ok", "grounded_fixes", "llm_calls", "latency_s"]
    print(f"\n{'metric':<20}" + "".join(f"{s:>12}" for s in systems))
    for metric in metrics:
        cells = "".join(f"{_cell(results['summary'][s][metric]):>12}" for s in systems)
        print(f"{metric:<20}{cells}")
    print(f"\n{len(results['cases'])} cases · model {results['model']}")


def _cell(value) -> str:
    return "n/a" if value is None else str(value)


def run(case_ids: list[str] | None = None, skip_baseline: bool = False, llm: StructuredLLM | None = None) -> dict:
    settings = get_settings()
    cases = json.loads(settings.scenarios_path.read_text(encoding="utf-8"))
    if case_ids:
        cases = [c for c in cases if c["id"] in case_ids]

    service = TroubleshootService(settings, llm=llm)
    validator = Validator(settings)
    per_case = []
    for case in cases:
        print(f"· {case['id']}", flush=True)
        entry = {"id": case["id"], "agentic": evaluate_agentic(service, case)}
        if not skip_baseline:
            entry["baseline"] = evaluate_baseline(service, validator, case)
        per_case.append(entry)

    systems = ["agentic"] + ([] if skip_baseline else ["baseline"])
    return {
        "model": service.llm.name,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "summary": {s: summarise([c[s] for c in per_case]) for s in systems},
        "cases": per_case,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", nargs="*", help="Scenario IDs to run (default: all)")
    parser.add_argument("--skip-baseline", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.llm_configured:
        raise SystemExit(f"{settings.llm_key_name} is not set; the evaluation calls the model.")

    results = run(args.cases, args.skip_baseline)
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"eval_{results['timestamp'].replace(':', '-')}.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print_table(results)
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
