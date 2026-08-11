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
_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


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

    @staticmethod
    def _safe_containers(values: list[str]) -> tuple[str, ...]:
        return tuple(str(x) for x in values if _CONTAINER_RE.fullmatch(str(x)))

    @staticmethod
    def _safe_services(values: list[str]) -> tuple[str, ...]:
        return tuple(str(x) for x in values if _UNIT_RE.fullmatch(str(x)))

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
            for name in self.services:
                result.append(self._systemd_status(name))
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

    def _docker_api(self, method: str, path: str) -> dict[str, Any]:
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
        status_line = header.splitlines()[0].decode("latin1") if header else ""
        status = int(status_line.split()[1]) if len(status_line.split()) > 1 else 0
        data = json.loads(body.decode() or "{}")
        if status >= 400:
            raise RuntimeError(data.get("message", f"Docker API HTTP {status}"))
        return data

    def _systemd_status(self, name: str) -> dict[str, Any]:
        try:
            code, out, error = self._run(
                ["systemctl", "show", name, "--no-pager", "--property=ActiveState,SubState,LoadState,Result,MainPID"]
            )
        except FileNotFoundError:
            return {"kind": "systemd", "name": name, "status": "unavailable", "error": "systemctl is not available in this container"}
        if code != 0:
            return {"kind": "systemd", "name": name, "status": "missing", "error": error}
        fields = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        return {
            "kind": "systemd",
            "name": name,
            "status": fields.get("ActiveState", "unknown"),
            "sub_status": fields.get("SubState"),
            "load_state": fields.get("LoadState"),
            "result": fields.get("Result"),
            "pid": fields.get("MainPID"),
        }

    def restart(self, kind: str, name: str) -> dict[str, Any]:
        if kind == "docker" and name in self.containers and self.docker_enabled:
            try:
                self._docker_api("POST", f"/containers/{quote(name, safe='')}/restart?t=10")
                return {"ok": True, "output": "Docker container restarted", "error": ""}
            except Exception as e:
                return {"ok": False, "output": "", "error": str(e)}
        elif kind == "systemd" and name in self.services and self.systemd_enabled:
            try:
                code, out, error = self._run(["systemctl", "restart", name], timeout=60)
            except FileNotFoundError:
                return {"ok": False, "output": "", "error": "systemctl is not available in this container"}
        else:
            return {"ok": False, "error": "target is not allowlisted"}
        return {"ok": code == 0, "output": out, "error": error}
