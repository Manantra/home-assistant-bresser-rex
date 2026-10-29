"""Optional camera entity for the printer's local MJPEG stream.

Some Adventurer III-compatible firmware briefly interrupts the camera HTTP
service while changing the built-in illumination. Retry short-lived failures
when opening the stream or fetching a preview; do not restart the camera or
touch the printer control session.
"""

from __future__ import annotations

import asyncio
import aiohttp
from aiohttp import web

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import (
    async_aiohttp_proxy_web,
    async_get_clientsession,
)
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CAMERA_ENABLED, DEFAULT_CAMERA_PORT

MAX_FRAME_BYTES = 3 * 1024 * 1024
OPEN_ATTEMPTS = 3
FRAME_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.4


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the camera unless disabled in integration options."""
    if entry.options.get(CONF_CAMERA_ENABLED, True):
        async_add_entities([RexCamera(entry.runtime_data)])


class RexCamera(Camera):
    """Proxy a local MJPEG stream and provide JPEG stills for the frontend."""

    _attr_has_entity_name = True
    _attr_translation_key = "camera"

    def __init__(self, coordinator) -> None:
        super().__init__()
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.serial}_camera"
        self._attr_device_info = coordinator.device_info
        self._url = f"http://{coordinator.host}:{DEFAULT_CAMERA_PORT}/?action=stream"

    @property
    def available(self) -> bool:
        # The camera HTTP service is independent of the TCP control session.
        return True

    async def _async_open_stream(self) -> aiohttp.ClientResponse:
        """Retry transient camera connection failures before starting a proxy.

        The returned response belongs to async_aiohttp_proxy_web, which closes
        it when the downstream stream ends.
        """
        session = async_get_clientsession(self.hass)
        for attempt in range(OPEN_ATTEMPTS):
            response = None
            try:
                response = await session.get(
                    self._url,
                    headers={"Cache-Control": "no-cache", "Connection": "close"},
                    timeout=aiohttp.ClientTimeout(
                        total=None, sock_connect=3, sock_read=30
                    ),
                )
                response.raise_for_status()
                return response
            except (aiohttp.ClientError, TimeoutError):
                if response is not None:
                    response.close()
                if attempt == OPEN_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
        raise RuntimeError("Unreachable MJPEG connection retry state")

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse | None:
        """Proxy MJPEG, retrying an upstream failure during initial connect."""
        return await async_aiohttp_proxy_web(
            self.hass,
            request,
            self._async_open_stream(),
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Extract a frame, retrying if the firmware temporarily drops MJPEG."""
        session = async_get_clientsession(self.hass)
        for attempt in range(FRAME_ATTEMPTS):
            try:
                async with session.get(
                    self._url,
                    headers={"Cache-Control": "no-cache", "Connection": "close"},
                    timeout=aiohttp.ClientTimeout(
                        total=3.5, sock_connect=2.5
                    ),
                ) as resp:
                    resp.raise_for_status()
                    buffer = bytearray()
                    async for chunk in resp.content.iter_chunked(8192):
                        buffer.extend(chunk)
                        start = buffer.find(b"\xff\xd8")
                        if start >= 0:
                            end = buffer.find(b"\xff\xd9", start + 2)
                            if end >= 0:
                                return bytes(buffer[start : end + 2])
                            if start > 0:
                                del buffer[:start]
                        if len(buffer) > MAX_FRAME_BYTES:
                            break
            except (aiohttp.ClientError, TimeoutError):
                # Retry silently: the camera often recovers immediately.
                pass

            if attempt < FRAME_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
        return None
