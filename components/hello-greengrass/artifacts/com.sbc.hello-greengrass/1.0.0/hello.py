"""Native-process Greengrass component — prints once; useful for local deployment smoke."""

from __future__ import annotations

import sys


def main() -> None:
    sys.stdout.write("hello-greengrass: ok\n")


if __name__ == "__main__":
    main()
