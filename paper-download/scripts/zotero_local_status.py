#!/usr/bin/env python3
"""Compatibility status entry; install zotero-workspace-library alongside paper-download."""
import json
import sys
from pathlib import Path

shared = Path(__file__).resolve().parents[2] / 'zotero-workspace-library' / 'scripts'
if not (shared / 'zotero_library' / 'connection.py').is_file():
    if __name__ == '__main__':
        print(json.dumps({'error': 'dependency_missing_zotero_library', 'read_only_ready': False}))
        raise SystemExit(1)
    raise ImportError('dependency_missing_zotero_library')
sys.path.insert(0, str(shared))
from zotero_library import connection

if __name__ == '__main__':
    raise SystemExit(connection.main())
# Retain the original import/patch contract of the status test suite.
sys.modules[__name__] = connection
