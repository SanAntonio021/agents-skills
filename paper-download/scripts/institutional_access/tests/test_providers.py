from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.request import Request

from institutional_access.providers import (
    IEEE,
    OPTICA,
    _DoiRedirectHandler,
    candidate_pdf_urls,
    get_provider,
    normalize_doi,
    pdf_button_node,
    resolve_article_url,
    safe_url,
)


class ProviderTests(unittest.TestCase):
    def test_ieee_and_optica_article_identity(self):
        self.assertEqual(
            get_provider("https://ieeexplore.ieee.org/document/11527108/"),
            IEEE,
        )
        article = (
            "https://opg.optica.org/oe/search.cfm?"
            "uri=oe-34-10-20001"
        )
        with self.assertRaises(ValueError):
            get_provider(article)
        fulltext = OPTICA.normalize_article_url(
            "https://opg.optica.org/oe/fulltext.cfm?uri=oe-34-10-20001"
        )
        self.assertIn("/oe/fulltext.cfm", fulltext)
        valid = OPTICA.normalize_article_url(
            "https://opg.optica.org/oe/abstract.cfm?"
            "uri=oe-34-10-20001&foo=bar"
        )
        self.assertEqual(valid, "https://opg.optica.org/oe/abstract.cfm?uri=oe-34-10-20001")
        redirected = OPTICA.normalize_article_url(
            "https://opg.optica.org/abstract.cfm?URI=oe-28-22-33084"
        )
        self.assertEqual(
            redirected,
            "https://opg.optica.org/abstract.cfm?uri=oe-28-22-33084",
        )

    def test_cross_origin_candidates_are_not_returned(self):
        state = {
            "href": "https://ieeexplore.ieee.org/document/11527108/",
            "meta": {"citation_pdf_url": "https://evil.example/paper.pdf"},
            "embeds": [
                "https://evil.example/frame.pdf",
                "https://ieeexplore.ieee.org/ieee-portal-ui/1.0.0/",
            ],
            "links": [
                {
                    "text": "PDF",
                    "href": "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=1",
                },
                {
                    "text": "PDF",
                    "href": "https://evil.example/paper.pdf",
                },
            ],
        }
        values = candidate_pdf_urls(IEEE, state)
        self.assertEqual(values[0].split("?", 1)[0], "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp")
        self.assertFalse(any("evil.example" in value for value in values))
        self.assertFalse(any(value.endswith("/ieee-portal-ui/1.0.0/") for value in values))

    def test_pdf_viewer_current_url_is_a_candidate(self):
        values = candidate_pdf_urls(
            OPTICA,
            {
                "href": "https://opg.optica.org/directpdfaccess/opaque/oe-28-22-33084.pdf?da=1",
                "contentType": "application/pdf",
                "meta": {},
                "embeds": [],
                "links": [],
            },
        )
        self.assertEqual(values[0], "https://opg.optica.org/directpdfaccess/opaque/oe-28-22-33084.pdf?da=1")

    def test_pdf_meta_precedes_visible_link(self):
        state = {
            "href": "https://opg.optica.org/oe/abstract.cfm?uri=oe-1-1-1",
            "meta": {"citation_pdf_url": "https://opg.optica.org/oe/viewmedia.cfm?uri=oe-1-1-1&seq=0"},
            "embeds": [],
            "links": [
                {
                    "text": "PDF Article",
                    "href": "https://opg.optica.org/oe/viewmedia.cfm?uri=oe-1-1-1&html=true",
                }
            ],
        }
        values = candidate_pdf_urls(OPTICA, state)
        self.assertTrue(values)
        self.assertIn("viewmedia.cfm", values[0])
        self.assertNotIn("html=true", values[0])

    def test_pdf_button_exact_and_decorated_name(self):
        self.assertIsNotNone(
            pdf_button_node(
                {"nodes": [{"role": "link", "name": "PDF", "ref": "r1"}]},
                IEEE,
            )
        )
        self.assertIsNotNone(
            pdf_button_node(
                {
                    "nodes": [
                        {
                            "role": "link",
                            "name": "PDF Article",
                            "ref": "r2",
                        }
                    ]
                },
                OPTICA,
            )
        )
        self.assertIsNone(
            pdf_button_node(
                {"nodes": [{"role": "link", "name": "PDF eReader", "ref": "r3"}]},
                IEEE,
            )
        )

    def test_doi_normalization(self):
        self.assertEqual(
            normalize_doi("https://doi.org/10.1109/TTHZ.2026.3695375"),
            "10.1109/tthz.2026.3695375",
        )
        with self.assertRaises(ValueError):
            normalize_doi("not-a-doi")

    def test_doi_url_resolves_to_supported_article(self):
        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return "https://ieeexplore.ieee.org/document/11527108/?tracking=1"

        opener = unittest.mock.Mock()
        opener.open.return_value = _Response()
        with patch("institutional_access.providers.urllib.request.build_opener", return_value=opener):
            provider, article = resolve_article_url(
                "https://doi.org/10.1109/TTHZ.2026.3695375"
            )
        self.assertEqual(provider, IEEE)
        self.assertEqual(article, "https://ieeexplore.ieee.org/document/11527108/")
        (request,) = opener.open.call_args.args
        self.assertEqual(request.full_url, "https://doi.org/10.1109/tthz.2026.3695375")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 15)

    def test_doi_redirect_cannot_leave_supported_hosts(self):
        handler = _DoiRedirectHandler()
        request = Request("https://doi.org/10.1109/example")
        with self.assertRaisesRegex(ValueError, "unsupported host"):
            handler.redirect_request(
                request, None, 302, "Found", {}, "https://127.0.0.1/private"
            )

    def test_safe_url_keeps_only_optics_article_identity(self):
        self.assertEqual(
            safe_url(
                "https://opg.optica.org/abstract.cfm?"
                "URI=oe-28-22-33084&token=secret"
            ),
            "https://opg.optica.org/abstract.cfm?uri=oe-28-22-33084",
        )
        self.assertEqual(
            safe_url(
                "https://ieeexplore.ieee.org/document/123/"
                "?arnumber=123&token=secret"
            ),
            "https://ieeexplore.ieee.org/document/123/",
        )


if __name__ == "__main__":
    unittest.main()
