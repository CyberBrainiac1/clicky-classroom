"""Standalone packaging entry point; never starts Clicky's assistant services."""
from classroom.ui import run

if __name__ == '__main__':
    raise SystemExit(run())
