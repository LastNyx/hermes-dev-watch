#!/usr/bin/env python3
"""Start the app from a checkout (also the PyInstaller entry point): python run.py [--root DIR ...]"""
import sys

from hermes_dev_watch.app import main

if __name__ == "__main__":
    sys.exit(main())
