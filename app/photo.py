"""
Validation for contact photos.

The service ships with an in-memory database and no object store, so a photo
travels with its contact as a base64 `data:` URL rather than as a file
reference. That makes the field user-supplied bytes on a hot path, so it is
checked on the way in: the declared media type must be one we allow, the
payload must decode as base64, the image must be small enough to keep responses
sane, and the decoded bytes must actually start with that format's signature.
"""

import base64
import binascii
import re

MAX_PHOTO_BYTES = 2 * 1024 * 1024
"""Largest decoded image accepted (2 MB)."""

ALLOWED_MEDIA_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")
"""Raster formats every browser renders. SVG is excluded: it can carry script."""

# Base64 inflates by 4/3, so an over-limit image can be rejected from the
# encoded length alone — before spending memory decoding it.
_MAX_ENCODED_LENGTH = (MAX_PHOTO_BYTES + 2) // 3 * 4

_TOO_LARGE = f"photo exceeds the maximum size of {MAX_PHOTO_BYTES // 1024 // 1024} MB"

_DATA_URL = re.compile(r"data:(?P<media_type>[\w.+-]+/[\w.+-]+);base64,(?P<payload>[A-Za-z0-9+/]+={0,2})")


def _sniff_media_type(data: bytes) -> str | None:
    """Return the media type implied by the image's magic bytes, if recognised."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_photo(value: str) -> str:
    """
    Return `value` unchanged if it is an acceptable photo, else raise `ValueError`.

    Pydantic turns the `ValueError` into the API's standard `422` response, so
    the messages here are written for the client that sent the image.
    """
    match = _DATA_URL.fullmatch(value)
    if match is None:
        raise ValueError("photo must be a base64 data URL, e.g. 'data:image/png;base64,iVBORw0KGgo...'")

    media_type = match["media_type"].lower()
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise ValueError(f"photo type '{media_type}' is not supported; use one of {', '.join(ALLOWED_MEDIA_TYPES)}")

    payload = match["payload"]
    if len(payload) > _MAX_ENCODED_LENGTH:
        raise ValueError(_TOO_LARGE)

    try:
        decoded = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("photo is not valid base64") from exc

    if len(decoded) > MAX_PHOTO_BYTES:
        raise ValueError(_TOO_LARGE)

    if _sniff_media_type(decoded) != media_type:
        raise ValueError(f"photo contents are not a valid {media_type} image")

    return value
