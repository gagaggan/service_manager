from service_manager.service_manager import ServiceManager


def test_only_allowlisted_targets_can_restart(monkeypatch):
    manager = ServiceManager({
        "docker": {"containers": ["plex"]},
        "systemd": {"services": ["nginx.service"]},
    })
    called = []

    def fake_run(args, timeout=15):
        called.append(args)
        return 0, "ok", ""

    monkeypatch.setattr(manager, "_run", fake_run)
    assert manager.restart("docker", "plex")["ok"]
    assert manager.restart("systemd", "nginx.service")["ok"]
    assert not manager.restart("docker", "--privileged")["ok"]
    assert called == [["docker", "restart", "plex"], ["systemctl", "restart", "nginx.service"]]

