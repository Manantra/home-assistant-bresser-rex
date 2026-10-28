"""Optional camera entity for the printer's local MJPEG stream."""

from __future__ import annotations

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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the camera unless disabled in integration options."""
    if entry.options.get(CONF_CAMERA_ENABLED, True):
        async_add_entities([RexCamera(entry.runtime_data)])


class RexCamera(Camera):
    """Proxy MJPEG video and return JPEG stills when requested."""

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
        # Camera port 8080 is independent of the TCP control session. A busy
        # printer must not hide an otherwise working camera stream.
        return True

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse | None:
        """Proxy an MJPEG stream without exposing the printer to the Internet."""
        session = async_get_clientsession(self.hass)
        return await async_aiohttp_proxy_web(
            self.hass,
            request,
            session.get(
                self._url,
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=30),
            ),
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Extract a frame from MJPEG; no separate still-image endpoint required."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                self._url, timeout=aiohttp.ClientTimeout(total=7, sock_connect=4)
            ) as resp:
                resp.raise_for_status()
                buffer = bytearray()
                async for chunk in resp.content.iter_chunked(8192):
                    buffer.extend(chunk)
                    start = buffer.find(b"\xff\xd8")
                    if start >= 0:
                        end = buffer.find(b"\xff\xd9", start + 2)
                        if end >= 0:
                            return bytes(buffer[start:end + 2])
                        if start > 0:
                            del buffer[:start]
                    if len(buffer) > MAX_FRAME_BYTES:
                        return None
        except (aiohttp.ClientError, TimeoutError):
            return None
        return None
