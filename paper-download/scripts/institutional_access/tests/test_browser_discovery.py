from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from institutional_access.browser import discover_web_access_checker


class BrowserDiscoveryTests(unittest.TestCase):
    def test_environment_override(self):
        with tempfile.TemporaryDirectory() as root:
            checker = Path(root) / "check-deps.mjs"
            checker.write_text("// test", encoding="utf-8")
            old = os.environ.get("PAPER_DOWNLOAD_WEB_ACCESS_CHECKER")
            try:
                os.environ["PAPER_DOWNLOAD_WEB_ACCESS_CHECKER"] = str(checker)
                self.assertEqual(discover_web_access_checker(), checker)
            finally:
                if old is None:
                    os.environ.pop("PAPER_DOWNLOAD_WEB_ACCESS_CHECKER", None)
                else:
                    os.environ["PAPER_DOWNLOAD_WEB_ACCESS_CHECKER"] = old


if __name__ == "__main__":
    unittest.main()
