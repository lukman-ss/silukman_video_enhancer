"""Desktop notification command planning."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Notification:
    title: str
    message: str


def notification_command(notification: Notification, system: str | None = None) -> list[str]:
    os_name = system or platform.system()
    if os_name == "Darwin":
        return [
            "osascript",
            "-e",
            f'display notification "{notification.message}" with title "{notification.title}"',
        ]
    if os_name == "Linux":
        return ["notify-send", notification.title, notification.message]
    if os_name == "Windows":
        return ["powershell", "-Command", f"New-BurntToastNotification -Text '{notification.title}', '{notification.message}'"]
    return []


def send_notification(notification: Notification, system: str | None = None) -> bool:
    command = notification_command(notification, system)
    if not command:
        return False
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0
