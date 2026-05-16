from __future__ import annotations

import argparse
import json
import sys

from . import agent, patents, store
from .nvidia_client import load_dotenv


COMMANDS = {"fetch-spec", "parse", "search", "plan", "ask", "research", "patent-search", "patent-background"}


def run_research(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    try:
        report = agent.ask(
            args.question,
            auto_fetch=not args.no_auto_fetch,
            specs=args.spec,
            limit=args.limit,
            model=args.model,
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")
    print(report)
    if not args.no_save:
        print(f"\nSaved: {agent.save_run(args.question, report)}")


def main() -> None:
    load_dotenv()
    argv = sys.argv[1:]
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv = ["research"] + argv

    parser = argparse.ArgumentParser(
        description="Dedicated 3GPP research agent powered by NVIDIA NIM.",
        epilog='最简单用法：python -m agent3gpp "你的 3GPP 研究议题"',
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    fetch = sub.add_parser("fetch-spec")
    fetch.add_argument("--spec", required=True)

    parse = sub.add_parser("parse")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)

    plan_cmd = sub.add_parser("plan")
    plan_cmd.add_argument("question")
    plan_cmd.add_argument("--model")

    patent_search = sub.add_parser("patent-search", help="Search Google Patents for feature pain-point background")
    patent_search.add_argument("query")
    patent_search.add_argument("--limit", type=int, default=5)

    patent_background = sub.add_parser("patent-background", help="Fetch patent Background text from a patent URL")
    patent_background.add_argument("url")

    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--spec", action="append", default=[])
    ask.add_argument("--no-auto-fetch", action="store_true")
    ask.add_argument("--model")
    ask.add_argument("--limit", type=int, default=12)
    ask.add_argument("--no-save", action="store_true", help="Do not write the report to runs/")

    research = sub.add_parser("research", help="Run full agentic research from a topic")
    research.add_argument("question")
    research.add_argument("--spec", action="append", default=[])
    research.add_argument("--no-auto-fetch", action="store_true")
    research.add_argument("--model")
    research.add_argument("--limit", type=int, default=12)
    research.add_argument("--no-save", action="store_true", help="Do not write the report to runs/")

    args = parser.parse_args(argv)
    if args.cmd == "fetch-spec":
        print(store.fetch_spec(args.spec))
    elif args.cmd == "parse":
        docs = store.parse_all()
        store.build_db()
        print(f"parsed={len(docs)} db={store.DB}")
    elif args.cmd == "search":
        print(json.dumps(store.search(args.query, args.limit), ensure_ascii=False, indent=2))
    elif args.cmd == "plan":
        try:
            research_plan = agent.plan(args.question, model=args.model)
        except Exception as exc:
            parser.exit(2, f"error: {exc}\n")
        print(json.dumps(research_plan.__dict__, ensure_ascii=False, indent=2))
    elif args.cmd == "patent-search":
        try:
            print(patents.dumps(patents.search_patents(args.query, limit=args.limit)))
        except Exception as exc:
            parser.exit(2, f"error: {exc}\n")
    elif args.cmd == "patent-background":
        try:
            print(patents.dumps(patents.fetch_patent_background(args.url)))
        except Exception as exc:
            parser.exit(2, f"error: {exc}\n")
    elif args.cmd == "ask":
        run_research(parser, args)
    elif args.cmd == "research":
        run_research(parser, args)


if __name__ == "__main__":
    main()
