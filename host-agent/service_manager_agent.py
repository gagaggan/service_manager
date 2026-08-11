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


def allowed_services():
    try:
        data = json.loads(Path(CONFIG_PATH).read_text())
        return {x for x in data.get("services", []) if UNIT_RE.fullmatch(x)}
    except (OSError, json.JSONDecodeError):
        return set()


def systemctl(args):
    return subprocess.run(
        ["/usr/bin/systemctl", *args],
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
            service = request.get("service", "")
            action = request.get("action", "")
            if service not in allowed_services():
                raise ValueError("service is not allowlisted")
            if action == "status":
                proc = systemctl(["show", service, "--no-pager", "--property=ActiveState,SubState,LoadState,Result,MainPID"])
                fields = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
                data = {
                    "status": fields.get("ActiveState", "unknown"),
                    "sub_status": fields.get("SubState"),
                    "load_state": fields.get("LoadState"),
                    "result": fields.get("Result"),
                    "pid": fields.get("MainPID"),
                }
            elif action == "restart":
                proc = systemctl(["restart", service])
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
