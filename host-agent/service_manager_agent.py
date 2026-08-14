#!/usr/bin/env python3
"""Small allowlisted host-side systemd agent for FlaskFarm."""

import json
import os
import re
import socketserver
import subprocess
from pathlib import Path


SOCKET_PATH = os.environ.get("SERVICE_MANAGER_AGENT_SOCKET", "/run/service-manager-agent.sock")
CONFIG_PATH = os.environ.get("SERVICE_MANAGER_AGENT_CONFIG", "/etc/service-manager-agent/services.json")
UNIT_RE = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")
USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,31}$")


def allowed_services():
    try:
        data = json.loads(Path(CONFIG_PATH).read_text())
        result = {}
        for value in data.get("services", []):
            if isinstance(value, str) and UNIT_RE.fullmatch(value):
                result[value] = {"name": value, "scope": "system"}
            elif isinstance(value, dict):
                name = str(value.get("name", ""))
                scope = str(value.get("scope", "system"))
                user = str(value.get("user", ""))
                if UNIT_RE.fullmatch(name) and scope == "system":
                    result[name] = {"name": name, "scope": scope}
                elif UNIT_RE.fullmatch(name) and scope == "user" and USER_RE.fullmatch(user):
                    result[name] = {"name": name, "scope": scope, "user": user}
        return result
    except (OSError, json.JSONDecodeError):
        return set()


def systemctl(target, args):
    command = ["/usr/bin/systemctl"]
    if target["scope"] == "user":
        command += ["--user", "--machine", f"{target['user']}@.host"]
    return subprocess.run(
        [*command, *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={"PATH": "/usr/bin:/bin", "SYSTEMD_COLORS": "0"},
    )


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            request = json.loads(self.rfile.readline(65536).decode())
            target = request.get("target", {})
            service = target.get("name", "")
            action = request.get("action", "")
            allowlisted = allowed_services()
            if action == "configure":
                services = request.get("services", [])
                normalized = {}
                for target_item in services:
                    if not isinstance(target_item, dict):
                        raise ValueError("invalid service target")
                    name = target_item.get("name", "")
                    scope = target_item.get("scope", "system")
                    user = target_item.get("user", "")
                    if not UNIT_RE.fullmatch(name):
                        raise ValueError("invalid service name")
                    if scope == "system":
                        normalized[name] = {"name": name, "scope": scope}
                    elif scope == "user" and USER_RE.fullmatch(user):
                        normalized[name] = {"name": name, "scope": scope, "user": user}
                    else:
                        raise ValueError("invalid service target")
                Path(CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)
                temporary = Path(CONFIG_PATH).with_suffix(".tmp")
                temporary.write_text(json.dumps({"services": list(normalized.values())}, indent=2) + "\n")
                os.replace(temporary, CONFIG_PATH)
                self.wfile.write((json.dumps({"ok": True, "data": {"count": len(normalized)}}) + "\n").encode())
                return
            if action == "list":
                proc = subprocess.run(
                    ["/usr/bin/systemctl", "list-unit-files", "--type=service", "--no-legend", "--no-pager"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                    env={"PATH": "/usr/bin:/bin", "SYSTEMD_COLORS": "0"},
                )
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.strip() or "systemctl list-unit-files failed")
                services = [
                    line.split(None, 1)[0]
                    for line in proc.stdout.splitlines()
                    if line.split() and UNIT_RE.fullmatch(line.split(None, 1)[0])
                ]
                self.wfile.write((json.dumps({"ok": True, "data": {"services": services}}) + "\n").encode())
                return
            if service not in allowlisted or allowlisted[service] != target:
                raise ValueError("service is not allowlisted")
            if action == "status":
                proc = systemctl(target, ["show", service, "--no-pager", "--property=ActiveState,SubState,LoadState,Result,MainPID"])
                fields = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
                data = {
                    "status": fields.get("ActiveState", "unknown"),
                    "sub_status": fields.get("SubState"),
                    "load_state": fields.get("LoadState"),
                    "result": fields.get("Result"),
                    "pid": fields.get("MainPID"),
                }
            elif action in ("start", "stop", "restart"):
                proc = systemctl(target, [action, service])
                data = {"output": proc.stdout.strip()}
            else:
                raise ValueError("unsupported action")
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or "systemctl failed")
            response = {"ok": True, "data": data}
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        self.wfile.write((json.dumps(response) + "\n").encode())


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main():
    path = Path(SOCKET_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    server = Server(str(path), Handler)
    os.chmod(path, 0o660)
    server.serve_forever()


if __name__ == "__main__":
    main()
