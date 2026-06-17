"""CLI entry point for the kst deprecation wrapper."""

import sys
from importlib.metadata import version


def main() -> None:
    print("warning: kst is deprecated; use iructl instead.", file=sys.stderr)

    if "--version" in sys.argv[1:]:
        print(f"kst {version('kst')}, using iructl {version('iructl')}")
        sys.exit(0)

    import iructl

    iructl.main()
