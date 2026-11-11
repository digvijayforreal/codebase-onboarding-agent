"""Command-line entry points: run the server or analyse a repo in the terminal."""
from __future__ import annotations

import argparse
import json

from .config import settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="onboard", description="Codebase Onboarding Agent")
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="Run the web app")
    serve.add_argument("--host", default=settings.host)
    serve.add_argument("--port", type=int, default=settings.port)

    an = sub.add_parser("analyze", help="Analyse a repo and print the difficulty map")
    an.add_argument("source", help="Local path or git URL")
    an.add_argument("--top", type=int, default=15)

    args = parser.parse_args()

    if args.cmd == "serve" or args.cmd is None:
        import uvicorn

        uvicorn.run(
            "onboarding_agent.web.app:app",
            host=getattr(args, "host", settings.host),
            port=getattr(args, "port", settings.port),
            reload=False,
        )
    elif args.cmd == "analyze":
        from .pipeline import analyze_repo

        report, _ = analyze_repo(args.source)
        print(f"\n{report.name}: {report.total_files} files, "
              f"{report.total_commits} commits, langs={report.languages}\n")
        print(f"{'DIFF':>5}  {'CPLX':>5}  {'INST':>5}  {'HOT':>5}  {'CTR':>5}  path")
        for f in report.files[:args.top]:
            print(
                f"{f.difficulty_score:5.1f}  {f.complexity_score:5.1f}  "
                f"{f.instability_score:5.1f}  {f.hotspot_forecast:5.1f}  "
                f"{f.centrality:5.1f}  {f.path}"
            )
        print()


if __name__ == "__main__":
    main()
