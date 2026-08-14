"""Safe, allowlisted service operations used by the FlaskFarm plugin."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from urllib.parse import quote
from dataclasses import dataclass
from typing import Any


_UNIT_RE = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")
_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,31}$")
_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

_PROTECTED_SYSTEMD_PREFIXES = (
    "systemd-", "dbus", "getty@", "serial-getty@", "user@", "session-",
    "network", "NetworkManager", "wpa_supplicant", "docker", "containerd",
    "ssh", "sshd", "cron", "rsyslog", "polkit", "udev", "modprobe@",
    "apt-", "unattended-upgrades", "snap", "service-manager-agent",
)



@dataclass(frozen=True)
class ServiceTarget:
    kind: str
    name: str


class ServiceManager:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        docker = config.get("docker", {})
        systemd = config.get("systemd", {})
        self.docker_enabled = bool(docker.get("enabled", True))
        self.systemd_enabled = bool(systemd.get("enabled", True))
        self.containers = self._safe_containers(docker.get("containers", []))
        self.services = self._safe_services(systemd.get("services", []))
        self.docker_socket = os.environ.get("SERVICE_MANAGER_DOCKER_SOCKET", "/var/run/docker.sock")
        self.systemd_agent_socket = os.environ.get(
            "SERVICE_MANAGER_SYSTEMD_SOCKET", "/run/service-manager-agent.sock"
        )

    def configure_from_settings(self, model_setting) -> None:
        docker_names = model_setting.get_list("service_docker_containers") or []
        systemd_values = model_setting.get_list("service_systemd_services") or []
        systemd_targets = []
        for value in systemd_values:
            parts = [x.strip() for x in value.split("|", 2)]
            if len(parts) == 3 and parts[0] == "user":
                systemd_targets.append({"name": parts[2], "scope": "user", "user": parts[1]})
            else:
                systemd_targets.append(value)
        self.containers = self._safe_containers(docker_names)
        self.services = self._safe_services(systemd_targets)

    def sync_systemd_allowlist(self) -> dict[str, Any]:
        try:
            self._systemd_agent("configure", list(self.services))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _safe_containers(values: list[str]) -> tuple[str, ...]:
        return tuple(str(x) for x in values if _CONTAINER_RE.fullmatch(str(x)))

    @staticmethod
    def _safe_services(values: list[Any]) -> tuple[dict[str, str], ...]:
        result = []
        for value in values:
            if isinstance(value, str) and _UNIT_RE.fullmatch(value):
                result.append({"name": value, "scope": "system"})
            elif isinstance(value, dict):
                name = str(value.get("name", ""))
                scope = str(value.get("scope", "system"))
                user = str(value.get("user", ""))
                if _UNIT_RE.fullmatch(name) and scope == "system":
                    result.append({"name": name, "scope": scope})
                elif _UNIT_RE.fullmatch(name) and scope == "user" and _USER_RE.fullmatch(user):
                    result.append({"name": name, "scope": scope, "user": user})
        return tuple(result)

    def _run(self, args: list[str], timeout: int = 15) -> tuple[int, str, str]:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def list_status(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if self.docker_enabled:
            for name in self.containers:
                result.append(self._docker_status(name))
        if self.systemd_enabled:
            for target in self.services:
                result.append(self._systemd_status(target))
        return result

    def _docker_status(self, name: str) -> dict[str, Any]:
        try:
            data = self._docker_api("GET", f"/containers/{quote(name, safe='')}/json")
            state = data.get("State", {})
        except FileNotFoundError:
            return {"kind": "docker", "name": name, "status": "unavailable", "error": f"Docker socket not found: {self.docker_socket}"}
        except Exception as e:
            return {"kind": "docker", "name": name, "status": "unavailable", "error": str(e)}
        health = state.get("Health") or {}
        return {
            "kind": "docker",
            "name": name,
            "status": state.get("Status", "unknown"),
            "running": bool(state.get("Running")),
            "health": health.get("Status"),
            "started_at": state.get("StartedAt"),
            "exit_code": state.get("ExitCode"),
        }

    def _docker_api(self, method: str, path: str) -> Any:
        """Call the local Docker Engine API without requiring docker CLI."""
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.settimeout(10)
            client.connect(self.docker_socket)
            request = (
                f"{method} {path} HTTP/1.1\r\n"
                "Host: docker\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode()
            client.sendall(request)
            chunks = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            client.close()
        raw = b"".join(chunks)
        header, _, body = raw.partition(b"\r\n\r\n")
        if b"transfer-encoding: chunked" in header.lower():
            decoded = b""
            while body:
                size_end = body.find(b"\r\n")
                if size_end < 0:
                    break
                size = int(body[:size_end].split(b";", 1)[0], 16)
                if size == 0:
                    break
                start = size_end + 2
                decoded += body[start:start + size]
                body = body[start + size + 2:]
            body = decoded
        status_line = header.splitlines()[0].decode("latin1") if header else ""
        status = int(status_line.split()[1]) if len(status_line.split()) > 1 else 0
        data = json.loads(body.decode() or "{}")
        if status >= 400:
            raise RuntimeError(data.get("message", f"Docker API HTTP {status}"))
        return data

    @staticmethod
    def _is_manageable_systemd_unit(name: str) -> bool:
        """Hide host-critical units from new selections while preserving saved ones."""
        return not name.startswith(_PROTECTED_SYSTEMD_PREFIXES)

    def list_candidates(self) -> dict[str, Any]:
        """Return selectable host services without changing the allowlist."""
        candidates: dict[str, Any] = {"docker": [], "systemd": [], "errors": {}}
        docker_names = set(self.containers)
        if self.docker_enabled:
            try:
                containers = self._docker_api("GET", "/containers/json?all=1")
                docker_names.update(
                    str(name).lstrip("/")
                    for container in containers
                    for name in container.get("Names", [])
                    if _CONTAINER_RE.fullmatch(str(name).lstrip("/"))
                )
            except Exception as e:
                candidates["errors"]["docker"] = str(e)
        candidates["docker"] = sorted(docker_names, key=str.lower)

        systemd_names: dict[str, str] = {}
        if self.systemd_enabled:
            try:
                services = self._systemd_agent("list", None).get("services", [])
                systemd_names.update(
                    (str(name), str(name))
                    for name in services
                    if _UNIT_RE.fullmatch(str(name))
                    and self._is_manageable_systemd_unit(str(name))
                )
            except Exception as e:
                candidates["errors"]["systemd"] = str(e)
        for target in self.services:
            if target["scope"] == "user":
                value = f"user|{target['user']}|{target['name']}"
                label = f"{target['name']} (사용자: {target['user']})"
            else:
                value = target["name"]
                label = value
            systemd_names[value] = label
        candidates["systemd"] = [
            {"value": value, "label": label}
            for value, label in sorted(systemd_names.items(), key=lambda item: item[1].lower())
        ]
        return candidates

    def _systemd_status(self, target: dict[str, str]) -> dict[str, Any]:
        name = target["name"]
        try:
            result = self._systemd_agent("status", target)
            result.update({"kind": "systemd", "name": name})
            return result
        except FileNotFoundError:
            return {"kind": "systemd", "name": name, "status": "unavailable", "error": "systemd agent socket not found"}
        except Exception as e:
            return {"kind": "systemd", "name": name, "status": "unavailable", "error": str(e)}

    def _systemd_agent(self, action: str, target) -> dict[str, Any]:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.settimeout(10)
            client.connect(self.systemd_agent_socket)
            payload = {"action": action}
            if action == "configure":
                payload["services"] = target
            elif target is not None:
                payload["target"] = target
            client.sendall((json.dumps(payload) + "\n").encode())
            data = b""
            while not data.endswith(b"\n"):
                chunk = client.recv(65536)
                if not chunk:
                    break
                data += chunk
        finally:
            client.close()
        result = json.loads(data.decode() or "{}")
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "systemd agent request failed"))
        return result.get("data", {})

    def control(self, action: str, kind: str, name: str) -> dict[str, Any]:
        if action not in ('start', 'stop', 'restart'):
            return {'ok': False, 'error': 'unsupported action'}
        if kind == 'docker' and name in self.containers and self.docker_enabled:
            try:
                suffix = '?t=10' if action == 'stop' else ''
                self._docker_api('POST', f"/containers/{quote(name, safe='')}/{action}{suffix}")
                return {'ok': True, 'output': f'Docker container {action} completed', 'error': ''}
            except Exception as e:
                return {'ok': False, 'output': '', 'error': str(e)}
        if kind == 'systemd' and self.systemd_enabled:
            target = next((item for item in self.services if item['name'] == name), None)
            if target is None:
                return {'ok': False, 'error': 'target is not allowlisted'}
            try:
                self._systemd_agent(action, target)
                return {'ok': True, 'output': f'systemd service {action} completed', 'error': ''}
            except Exception as e:
                return {'ok': False, 'output': '', 'error': str(e)}
        return {'ok': False, 'error': 'target is not allowlisted'}

    def restart(self, kind: str, name: str) -> dict[str, Any]:
        return self.control('restart', kind, name)
