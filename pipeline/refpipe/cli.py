import argparse
import importlib
import sys

from refpipe.errors import RefpipeError

MODULES: tuple[str, ...] = ("compile", "frommidi", "cut", "check", "credits", "preview")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="refpipe", description="UltraStar reference tooling")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in MODULES:
        importlib.import_module(f"refpipe.{name}").add_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except RefpipeError as exc:
        print(f"refpipe: {exc}", file=sys.stderr)
        return 2
