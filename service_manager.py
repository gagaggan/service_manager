"""Safe, allowlisted service operations used by the FlaskFarm plugin."""

from __future__ import annotations

import json
import os
import re
import subprocess
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
        code, out, error = self._run(
            ["docker", "inspect", "--format", "{{json .State}}", name]
        )
        if code != 0:
            return {"kind": "docker", "name": name, "status": "missing", "error": error}
        try:
            state = json.loads(out)
        except json.JSONDecodeError:
            return {"kind": "docker", "name": name, "status": "unknown", "error": "invalid docker output"}
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

    def _systemd_status(self, name: str) -> dict[str, Any]:
        code, out, error = self._run(
            ["systemctl", "show", name, "--no-pager", "--property=ActiveState,SubState,LoadState,Result,MainPID"]
        )
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
            code, out, error = self._run(["docker", "restart", name], timeout=60)
        elif kind == "systemd" and name in self.services and self.systemd_enabled:
            code, out, error = self._run(["systemctl", "restart", name], timeout=60)
        else:
            return {"ok": False, "error": "target is not allowlisted"}
        return {"ok": code == 0, "output": out, "error": error}

