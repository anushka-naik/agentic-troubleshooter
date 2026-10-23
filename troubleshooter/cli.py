"""Command-line entry point.

python -m troubleshooter.cli --scenario none-sort
python -m troubleshooter.cli --query "TypeError: ..." --code-file app.py
python -m troubleshooter.cli --build-index
"""

import argparse
import json
import sys
from pathlib import Path

from troubleshooter.config import get_settings
from troubleshooter.rag.indexer import build_index
from troubleshooter.schemas import TroubleshootRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Investigate a Python error with the agent team.")
    parser.add_argument("--scenario", help="ID of a scenario in data/scenarios.json")
    parser.add_argument("--query", help="Error message, traceback or question")
    parser.add_argument("--code-file", type=Path, help="File containing the failing code")
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON")
    parser.add_argument("--build-index", action="store_true", help="Rebuild the documentation index and exit")
    args = parser.parse_args()

    settings = get_settings()
    if args.build_index:
        print(f"Indexed {build_index(settings)} chunks into {settings.index_dir}")
        return 0

    if args.scenario:
        scenarios = {s["id"]: s for s in json.loads(settings.scenarios_path.read_text(encoding="utf-8"))}
        if args.scenario not in scenarios:
            parser.error(f"unknown scenario; choose from: {', '.join(scenarios)}")
        request = TroubleshootRequest(query=scenarios[args.scenario]["query"], code=scenarios[args.scenario]["code"])
    elif args.query:
        code = args.code_file.read_text(encoding="utf-8") if args.code_file else None
        request = TroubleshootRequest(query=args.query, code=code)
    else:
        parser.error("provide --scenario or --query")

    if not settings.llm_configured:
        parser.error(f"{settings.llm_key_name} is not set; add it to .env")

    from troubleshooter.service import TroubleshootService

    service = TroubleshootService(settings)
    try:
        for event in service.stream(request):
            if event["event"] == "step":
                data = event["data"]
                print(f"[{data['agent']:>18}] {data['summary']} ({data['duration_ms']} ms)", file=sys.stderr)
            elif event["event"] == "report":
                report = event["data"]
                print(json.dumps(report, indent=2) if args.json else report["markdown"])
    except Exception as exc:
        print(f"Investigation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
