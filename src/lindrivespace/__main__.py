"""``python -m lindrivespace`` entry point.

``--collect`` runs the headless collector (no GTK), which is what the
scheduler's systemd user timer executes; everything else starts the GUI.
"""

import sys


def _main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "--collect":
        from lindrivespace.collector import main as collect_main

        return collect_main(argv[1:])
    from lindrivespace.app import main

    return main()


if __name__ == "__main__":
    sys.exit(_main())
