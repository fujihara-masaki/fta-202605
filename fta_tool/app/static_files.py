"""Static files the browser revalidates before every use (PR-C).

docs/static-assets-cache-control-plan.md, section 5:
* the 200 and 304 responses carry ``Cache-Control: no-cache``, so a stored
  copy is used only after the server has confirmed it (SP-01, SP-02);
* the ETag is a hash of the file's content, never of its time and size: a
  replacement that keeps the size and the time, or moves the time back (an
  older working tree, a rollback), still gets another ETag (SP-03);
* ``If-None-Match`` decides alone when the request has it, and
  ``If-Modified-Since`` is only used without it (SP-04, SP-05; RFC 9110
  13.1.3 and 13.2.2). Starlette 0.37.2 also answers 304 when the ETags differ
  but ``If-Modified-Since`` is not older than the file, which browsers send
  together with ``If-None-Match``.

Everything else is Starlette's StaticFiles unchanged: the path lookup and its
refusal of paths that leave the directory once normalised, the 404 and 405
answers, Content-Type and Last-Modified (SP-06 to SP-08).

The hash is computed for every request and never reused by time and size,
which would bring back the replacements above. Files are replaced while the
server is stopped (plan 3.5), so the hash and the body sent belong together.
"""

from __future__ import annotations

import hashlib
import os
import re

from starlette.datastructures import Headers
from starlette.responses import FileResponse, Response
from starlette.staticfiles import NotModifiedResponse, StaticFiles
from starlette.types import Scope

CACHE_CONTROL = "no-cache"
_CHUNK = 64 * 1024


def content_etag(path: str | os.PathLike) -> str:
    """Strong ETag of the file's bytes (the first 32 hex digits of SHA-256)."""
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(_CHUNK), b""):
            digest.update(chunk)
    return f'"{digest.hexdigest()[:32]}"'


# One entity-tag of If-None-Match (RFC 9110 8.8.3): an optional W/ and a
# quoted opaque tag, whose characters may include "," and "*".
_ENTITY_TAG = re.compile(r'\s*(?:W/)?("[^"]*")\s*(?:,|$)')


def etag_matches(if_none_match: str, etag: str) -> bool:
    """Weak comparison of If-None-Match with the current ETag. The field is
    either "*" alone (any current representation) or a list of entity-tags
    separated by commas, with or without W/; a "*" or a comma inside a quoted
    tag is part of that tag. A malformed field matches nothing."""
    value = if_none_match.strip()
    if value == "*":
        return True
    current = etag[2:] if etag.startswith("W/") else etag
    position = 0
    while position < len(value):
        match = _ENTITY_TAG.match(value, position)
        if match is None:
            return False
        if match.group(1) == current:
            return True
        position = match.end()
    return False


class RevalidatedStaticFiles(StaticFiles):
    def file_response(
        self,
        full_path: str | os.PathLike,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        # FileResponse fills Content-Length and Last-Modified from the stat
        # result and keeps the ETag given here (set_stat_headers uses
        # setdefault).
        response = FileResponse(
            full_path,
            status_code=status_code,
            stat_result=stat_result,
            headers={"etag": content_etag(full_path), "cache-control": CACHE_CONTROL},
        )
        if self.is_not_modified(response.headers, Headers(scope=scope)):
            return NotModifiedResponse(response.headers)  # keeps cache-control and etag
        return response

    def is_not_modified(self, response_headers: Headers, request_headers: Headers) -> bool:
        if_none_match = request_headers.get("if-none-match")
        if if_none_match is not None:
            return etag_matches(if_none_match, response_headers["etag"])
        # Without If-None-Match Starlette's check only looks at
        # If-Modified-Since (SP-05).
        return super().is_not_modified(response_headers, request_headers)
