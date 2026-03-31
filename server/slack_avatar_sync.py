from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Sync Anima avatar images to Slack bot profile photos.

On server startup, for each per-Anima Slack bot:
1. Locate the Anima's avatar image (avatar_bustup_realistic.png)
2. Crop to a square (head region) and resize to 512x512
3. Upload to Slack via ``users.setPhoto`` API

If ``users.setPhoto`` is not available for bot tokens (Slack may restrict
this to user tokens), the failure is logged gracefully and the user is
advised to upload manually via api.slack.com.
"""

import io
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("animaworks.slack_avatar_sync")

_SLACK_SET_PHOTO_URL = "https://slack.com/api/users.setPhoto"
_ICON_SIZE = 512
_SLACK_TIMEOUT = 30.0

# Preferred asset filenames in priority order
_ICON_CANDIDATES = [
    "icon_realistic.png",
    "icon.png",
    "avatar_bustup_realistic.png",
    "avatar_bustup.png",
]


def _find_avatar(anima_dir: Path) -> Path | None:
    """Find the best avatar image for an Anima."""
    assets_dir = anima_dir / "assets"
    if not assets_dir.is_dir():
        return None
    for candidate in _ICON_CANDIDATES:
        path = assets_dir / candidate
        if path.is_file():
            return path
    return None


def _prepare_icon(image_path: Path) -> bytes:
    """Crop and resize an avatar image to a square icon.

    For bustup images (portrait orientation), crops the top portion
    (head area) to a square, then resizes to 512x512.
    For already-square images, just resizes.

    Returns PNG bytes.
    """
    from PIL import Image

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        w, h = img.size

        if w == h:
            # Already square
            cropped = img
        elif h > w:
            # Portrait (bustup): crop top square (head region)
            cropped = img.crop((0, 0, w, w))
        else:
            # Landscape: center crop
            offset = (w - h) // 2
            cropped = img.crop((offset, 0, offset + h, h))

        resized = cropped.resize((_ICON_SIZE, _ICON_SIZE), Image.LANCZOS)

        buf = io.BytesIO()
        resized.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


async def _set_bot_photo(token: str, image_bytes: bytes) -> dict[str, Any]:
    """Upload a profile photo via Slack's users.setPhoto API."""
    async with httpx.AsyncClient(timeout=_SLACK_TIMEOUT) as client:
        resp = await client.post(
            _SLACK_SET_PHOTO_URL,
            headers={"Authorization": f"Bearer {token}"},
            files={"image": ("icon.png", image_bytes, "image/png")},
        )
        resp.raise_for_status()
        return resp.json()


async def sync_avatars(
    app_map: dict[str, Any],
    animas_dir: Path,
    *,
    get_token: Any = None,
) -> int:
    """Sync Anima avatars to Slack bot profile photos.

    Args:
        app_map: Mapping of anima_name -> AsyncApp (from SlackSocketModeManager).
        animas_dir: Path to the animas directory.
        get_token: Optional callable(anima_name) -> token string.

    Returns:
        Number of successfully updated avatars.
    """
    updated = 0
    failed_names: list[str] = []

    for anima_name, app in app_map.items():
        if anima_name == "__shared__":
            continue

        token = app.client.token if hasattr(app, "client") else None
        if get_token:
            token = get_token(anima_name) or token
        if not token:
            continue

        anima_dir = animas_dir / anima_name
        avatar_path = _find_avatar(anima_dir)
        if not avatar_path:
            logger.debug("No avatar found for '%s'", anima_name)
            continue

        try:
            icon_bytes = _prepare_icon(avatar_path)
        except Exception:
            logger.warning(
                "Failed to prepare icon for '%s' from %s",
                anima_name,
                avatar_path,
                exc_info=True,
            )
            continue

        try:
            result = await _set_bot_photo(token, icon_bytes)
            if result.get("ok"):
                logger.info(
                    "Slack avatar updated for '%s' (from %s)",
                    anima_name,
                    avatar_path.name,
                )
                updated += 1
            else:
                error = result.get("error", "unknown")
                if error in ("not_allowed", "not_authed", "missing_scope"):
                    # Bot tokens typically can't use users.setPhoto
                    failed_names.append(anima_name)
                    logger.debug(
                        "users.setPhoto not available for bot '%s': %s",
                        anima_name,
                        error,
                    )
                else:
                    logger.warning(
                        "Slack avatar update failed for '%s': %s",
                        anima_name,
                        error,
                    )
        except Exception:
            failed_names.append(anima_name)
            logger.debug(
                "Failed to set Slack avatar for '%s'",
                anima_name,
                exc_info=True,
            )

    if failed_names and updated == 0:
        logger.info(
            "Slack avatar auto-sync not available (bot tokens may lack users:write scope). "
            "Upload manually at api.slack.com for: %s",
            ", ".join(sorted(failed_names)),
        )

    return updated
