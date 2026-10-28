"""Publisher-specific article and PDF recognition."""

from __future__ import annotations

import re
from dataclasses import dataclass
import urllib.error
import urllib.request
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit


OPTICA_JOURNALS = (
    "ol",
    "oe",
    "ao",
    "josaa",
    "josab",
    "optica",
    "prj",
    "boe",
    "ome",
    "osac",
    "aop",
)
DOI_HOSTS = {"doi.org", "dx.doi.org"}
ARTICLE_HOSTS = {"ieeexplore.ieee.org", "opg.optica.org"}


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    host: str
    article_pattern: re.Pattern[str]
    pdf_button_names: tuple[str, ...]

    def normalize_article_url(self, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != self.host
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not self.article_pattern.fullmatch(parsed.path)
        ):
            raise ValueError(f"not a supported {self.label} article URL")
        if self.id == "optica":
            query = parse_qs(parsed.query, keep_blank_values=True)
            uri = []
            for key, values in query.items():
                if key.lower() == "uri":
                    uri.extend(values)
            if len(uri) != 1 or not re.fullmatch(
                r"(?:" + "|".join(OPTICA_JOURNALS) + r")-[0-9]+-[0-9]+-[A-Za-z0-9]+",
                uri[0],
            ):
                raise ValueError("Optica article URL requires one uri parameter")
            return urlunsplit(
                ("https", self.host, parsed.path, urlencode({"uri": uri[0]}), "")
            )
        return urlunsplit(("https", self.host, parsed.path, "", ""))


IEEE = Provider(
    id="ieee",
    label="IEEE Xplore",
    host="ieeexplore.ieee.org",
    article_pattern=re.compile(r"/document/[0-9]+/?"),
    pdf_button_names=("pdf", "download pdf"),
)
OPTICA = Provider(
    id="optica",
    label="Optica Publishing Group",
    host="opg.optica.org",
    article_pattern=re.compile(
        r"(?:/(?:" + "|".join(OPTICA_JOURNALS) + r"))?/"
        r"(?:abstract|fulltext|viewmedia|view_article)\.cfm"
    ),
    pdf_button_names=("pdf article", "pdf", "download pdf"),
)


class _DoiRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            parsed = urlsplit(newurl)
            allowed = (
                parsed.scheme == "https"
                and parsed.hostname in DOI_HOSTS | ARTICLE_HOSTS
                and not parsed.username
                and not parsed.password
                and parsed.port in (None, 443)
            )
        except ValueError:
            allowed = False
        if not allowed:
            raise ValueError("DOI URL redirected to an unsupported host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def resolve_article_url(url: str) -> tuple[Provider, str]:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
    except ValueError as error:
        raise ValueError("article URL is invalid") from error
    if host in DOI_HOSTS:
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValueError("DOI URL must use HTTPS without credentials")
        doi = normalize_doi(unquote(parsed.path.lstrip("/")))
        opener = urllib.request.build_opener(_DoiRedirectHandler())
        request = urllib.request.Request(
            f"https://doi.org/{doi}",
            headers={"User-Agent": "paper-download/1.0"},
        )
        try:
            with opener.open(request, timeout=15) as response:
                url = response.geturl()
        except urllib.error.HTTPError as error:
            raise ValueError(f"DOI resolver returned HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ValueError("DOI URL could not be resolved") from error
        try:
            host = urlsplit(url).hostname
        except ValueError as error:
            raise ValueError("DOI resolved to an invalid article URL") from error
    if host == IEEE.host:
        IEEE.normalize_article_url(url)
        return IEEE, IEEE.normalize_article_url(url)
    if host == OPTICA.host:
        OPTICA.normalize_article_url(url)
        return OPTICA, OPTICA.normalize_article_url(url)
    if parsed.hostname in DOI_HOSTS:
        raise ValueError("DOI did not resolve to a supported IEEE Xplore or Optica article page")
    raise ValueError("only IEEE Xplore and Optica article URLs are supported")


def get_provider(url: str) -> Provider:
    return resolve_article_url(url)[0]


def normalize_doi(value: str) -> str:
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I)
    if not re.fullmatch(r"10\.[0-9]{4,9}/\S+", doi, flags=re.I):
        raise ValueError("DOI is invalid")
    return doi.lower()


def compact_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[invalid-url]"
    if parsed.scheme not in {"http", "https"}:
        return "[redacted-url]"
    path = parsed.path or "/"
    query = ""
    if parsed.hostname == OPTICA.host:
        uri = [
            value
            for key, value in parse_qs(parsed.query, keep_blank_values=True).items()
            if key.lower() == "uri"
        ]
        if len(uri) == 1 and uri[0]:
            query = urlencode({"uri": uri[0][0]})
    return urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))


def page_state_expression() -> str:
    return r"""(() => {
      const visible = e => !!e && e.getClientRects().length > 0;
      const absolute = value => {
        try {
          const url = new URL(value, location.href);
          return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
        } catch (_) {
          return '';
        }
      };
      const text = (document.body?.innerText || '').slice(0, 120000);
      const meta = Object.fromEntries(
        [...document.querySelectorAll('meta[name]')]
          .map(e => [e.name.toLowerCase(), e.content])
          .filter(([, value]) => typeof value === 'string')
      );
      const links = [...document.querySelectorAll('a[href]')]
        .map(e => ({text: (e.innerText || e.getAttribute('aria-label') || '').trim(), href: absolute(e.href)}))
        .filter(x => x.href)
        .slice(0, 500);
      const embeds = [...document.querySelectorAll('iframe[src], embed[src], object[data]')]
        .map(e => absolute(e.src || e.data))
        .filter(Boolean)
        .slice(0, 100);
      return {
        readyState: document.readyState,
        host: location.hostname,
        path: location.pathname,
        href: absolute(location.href),
        title: document.title,
        contentType: document.contentType || '',
        text,
        meta,
        links,
        embeds,
        challenge:
          /captcha|verify you are human|complete the security check|验证码/i.test(
            document.title + '\n' + text.slice(0, 12000)
          ) ||
          [...document.querySelectorAll('iframe')].some(
            e => visible(e) && /captcha|challenges\.cloudflare/i.test(e.src)
          ),
        accessSignals: [
          /access provided by/i.test(text),
          /brought to you by/i.test(text)
        ],
        loginSignals: [
          /institutional sign in/i.test(text),
          /sign in to access/i.test(text),
          /access through/i.test(text),
          /china carsi|access through carsi/i.test(text),
          /openathens|shibboleth/i.test(text)
        ],
        denialSignals: [
          /you do not have access/i.test(text),
          /purchase pdf/i.test(text),
          /get access/i.test(text),
          /sign in to access/i.test(text)
        ],
        openAccessSignals: [
          /open access/i.test(text),
          /creative commons/i.test(text),
          /cc by/i.test(text)
        ]
      };
    })()"""


def metadata_doi(state: dict) -> str | None:
    meta = state.get("meta") or {}
    for key in ("citation_doi", "dc.identifier", "doi", "prism.doi"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            try:
                return normalize_doi(value)
            except ValueError:
                continue
    return None


def candidate_pdf_urls(provider: Provider, state: dict) -> list[str]:
    values: list[tuple[str, int]] = []
    if state.get("contentType") == "application/pdf":
        current = state.get("href")
        if isinstance(current, str) and current:
            values.append((current, 110))
    meta = state.get("meta") or {}
    pdf_meta = meta.get("citation_pdf_url")
    if isinstance(pdf_meta, str) and pdf_meta:
        values.append((pdf_meta, 100))
    for href in state.get("embeds") or []:
        lowered = href.lower()
        path = urlsplit(href).path.lower()
        if (
            path.endswith(".pdf")
            or any(
                token in lowered
                for token in (
                    "/stamppdf/",
                    "getpdf.jsp",
                    "directpdfaccess",
                    "viewmedia.cfm",
                )
            )
        ):
            values.append((href, 90))
    for item in state.get("links") or []:
        text = (item.get("text") or "").lower()
        href = item.get("href") or ""
        lowered = href.lower()
        if any(token in lowered for token in ("stampPDF/getPDF.jsp", "directpdfaccess")):
            score = 95
        elif any(token in lowered for token in ("/stamppdf/", "getpdf.jsp")):
            score = 85
        elif any(token in lowered for token in ("stamp/stamp.jsp", "/viewmedia.cfm")):
            score = 75
        elif href.lower().split("?", 1)[0].endswith(".pdf"):
            score = 80
        elif "pdf" in text:
            score = 60
        else:
            continue
        if any(token in lowered for token in ("html=true", "supplementary", "erratum")):
            continue
        values.append((href, score))
    parsed_page = urlsplit(state.get("href") or "")
    filtered: list[tuple[str, int]] = []
    for value, score in list(values):
        try:
            parsed = urlsplit(value)
        except ValueError:
            continue
        if (
            parsed.scheme != "https"
            or parsed.hostname != provider.host
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            continue
        if provider.id == "optica":
            score += 10 if "directpdfaccess" in parsed.path else 0
        if provider.id == "ieee":
            score += 10 if "stamppdf" in parsed.path.lower() else 0
        if parsed_page.hostname == parsed.hostname:
            score += 2
        filtered.append((value, score))
    best: dict[str, int] = {}
    for value, score in sorted(filtered, key=lambda item: item[1], reverse=True):
        if not value or not value.startswith(("http://", "https://")):
            continue
        best[value] = max(score, best.get(value, -1))
    return [value for value, _ in sorted(best.items(), key=lambda item: item[1], reverse=True)]


def pdf_button_node(snapshot: dict, provider: Provider) -> dict | None:
    nodes = snapshot.get("nodes") or []
    for wanted in provider.pdf_button_names:
        for node in nodes:
            if node.get("disabled"):
                continue
            name = (node.get("name") or "").strip().lower()
            role = (node.get("role") or "").lower()
            if name == wanted and role in {"button", "link", "menuitem"} and node.get("ref"):
                return node
    for wanted in provider.pdf_button_names:
        for node in nodes:
            if node.get("disabled"):
                continue
            name = (node.get("name") or "").strip().lower()
            role = (node.get("role") or "").lower()
            if (
                name.startswith(wanted + " (")
                or name.startswith(wanted + "(")
                or name.startswith(wanted + " -")
            ) and role in {"button", "link", "menuitem"} and node.get("ref"):
                return node
    return None


def public_page_identity(state: dict, doi: str, provider: Provider) -> dict:
    found_doi = metadata_doi(state)
    return {
        "provider": provider.id,
        "host": state.get("host"),
        "title": (state.get("title") or "")[:500],
        "doi": doi,
        "page_doi": found_doi,
        "doi_match": found_doi == doi if found_doi else None,
    }
