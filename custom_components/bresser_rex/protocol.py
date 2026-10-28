"""Small, local-only TCP client for the REX/Adventurer III protocol.

Each transaction obtains control with M601, issues only its required commands,
releases with M602 and closes its socket. All network I/O is synchronous;
Home Assistant runs it in an executor thread.
"""

from __future__ import annotations

import re
import socket
import time
from typing import Any

from .const import DEFAULT_TCP_PORT

MAX_REPLY = 16384
SOCKET_TIMEOUT = 5


class RexError(Exception):
    """A printer communication or response error."""


class RexBusy(RexError):
    """Another client holds the printer's control session."""


def _read_reply(sock: socket.socket) -> str:
    data = bytearray()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            raise RexError("Printer closed the connection unexpectedly")
        data.extend(chunk)
        if len(data) > MAX_REPLY:
            raise RexError("Printer reply is too large")
        normalized = bytes(data).replace(b"\r", b"")
        if re.search(rb"(?:^|\n)ok(?:\n|$)", normalized):
            return data.decode("utf-8", errors="replace")


def _command(sock: socket.socket, command: str) -> str:
    sock.sendall(("~" + command + "\r\n").encode("ascii"))
    response = _read_reply(sock)
    if "CMD " + command.split()[0] + " Received." not in response:
        raise RexError("Unexpected printer command reply")
    if re.search(r"(?im)^error:", response) or (
        not command.startswith("M601")
        and re.search(r"(?im)^control failed", response)
    ):
        raise RexError("Printer rejected the command")
    return response


def transaction(host: str, commands: list[str]) -> list[str]:
    """Run commands in a short-lived, exclusive control session."""
    try:
        with socket.create_connection((host, DEFAULT_TCP_PORT), timeout=SOCKET_TIMEOUT) as sock:
            sock.settimeout(SOCKET_TIMEOUT)
            acquired = False
            try:
                login = _command(sock, "M601 S1")
                if "Control Success" not in login:
                    raise RexBusy("Printer control session is busy")
                acquired = True
                time.sleep(0.2)  # Older firmware can need a short settling time.
                replies = [_command(sock, command) for command in commands]
                if any(command.startswith("M146") for command in commands):
                    time.sleep(0.5)  # Match the tested LED command timing.
                return replies
            finally:
                if acquired:
                    try:
                        _command(sock, "M602")
                    except (OSError, RexError):
                        # Socket closing also relinquishes the session.
                        pass
    except (TimeoutError, ConnectionError, OSError) as err:
        raise RexError("Cannot reach printer on the network") from err


def get_identity(host: str) -> dict[str, str]:
    reply = transaction(host, ["M115"])[0]
    info: dict[str, str] = {}
    for line in reply.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
    model = info.get("Machine Type", "")
    if not re.search(r"Adventurer\s*(?:III|3)\b", model, re.I):
        raise RexError("Device is not a supported Adventurer III")
    if not info.get("SN"):
        raise RexError("Printer did not report a serial number")
    return info


def _temperature(reply: str, key: str) -> tuple[float | None, float | None]:
    # Both compact (T0:23/0) and spaced/decimal firmware variants.
    match = re.search(
        rf"(?<!\w){re.escape(key)}:\s*(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)",
        reply,
    )
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def parse_readings(temperature: str, status: str, progress: str) -> dict[str, Any]:
    nozzle, nozzle_target = _temperature(temperature, "T0")
    bed, bed_target = _temperature(temperature, "B")
    match = re.search(r"(?m)^MachineStatus:[ \t]*([^\r\n]+)", status)
    machine_status = match.group(1).strip() if match else None
    match = re.search(r"(?m)^CurrentFile:[ \t]*([^\r\n]*)", status)
    current_file = match.group(1).strip() if match else None

    # M27 can say 'SD printing byte 0/100' even when the printer is READY.
    # A percentage is therefore valid ONLY during an active job.
    progress_percent = None
    if machine_status and (
        machine_status.startswith("BUILDING") or machine_status in ("PRINTING", "PAUSED")
    ):
        match = re.search(r"SD printing byte\s+(\d+)\s*/\s*(\d+)", progress)
        if match and int(match.group(2)) > 0:
            progress_percent = round(
                min(100.0, 100 * int(match.group(1)) / int(match.group(2))), 1
            )

    return {
        "nozzle": nozzle,
        "nozzle_target": nozzle_target,
        "bed": bed,
        "bed_target": bed_target,
        "machine_status": machine_status,
        "current_file": current_file or None,
        "progress": progress_percent,
    }


def get_readings(host: str) -> dict[str, Any]:
    temperature, status, progress = transaction(host, ["M105", "M119", "M27"])
    return parse_readings(temperature, status, progress)


def set_led(host: str, on: bool) -> None:
    channel = 255 if on else 0
    transaction(host, [f"M146 r{channel} g{channel} b{channel} F0"])
