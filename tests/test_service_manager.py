from service_manager.service_manager import ServiceManager


def test_only_allowlisted_targets_can_restart(monkeypatch):
    manager = ServiceManager({
        "docker": {"containers": ["plex"]},
        "systemd": {"services": ["nginx.service"]},
    })
    called = []

    def fake_docker_api(method, path):
        called.append(("docker", method, path))
        return {}

    def fake_systemd_agent(action, target):
        called.append(("systemd", action, target))
        return {}

    monkeypatch.setattr(manager, "_docker_api", fake_docker_api)
    monkeypatch.setattr(manager, "_systemd_agent", fake_systemd_agent)
    assert manager.restart("docker", "plex")["ok"]
    assert manager.restart("systemd", "nginx.service")["ok"]
    assert not manager.restart("docker", "--privileged")["ok"]
    assert called == [
        ("docker", "POST", "/containers/plex/restart"),
        ("systemd", "restart", {"name": "nginx.service", "scope": "system"}),
    ]


def test_list_candidates_is_read_only_and_validates_names(monkeypatch):
    manager = ServiceManager()

    def fake_docker_api(method, path):
        assert (method, path) == ("GET", "/containers/json?all=1")
        return [{"Names": ["/plex", "/bad name"]}, {"Names": ["/ff"]}]

    def fake_systemd_agent(action, target):
        assert (action, target) == ("list", None)
        return {"services": ["nginx.service", "bad unit", "plexmediaserver.service"]}

    monkeypatch.setattr(manager, "_docker_api", fake_docker_api)
    monkeypatch.setattr(manager, "_systemd_agent", fake_systemd_agent)
    assert manager.list_candidates() == {
        "docker": ["ff", "plex"],
        "systemd": ["nginx.service", "plexmediaserver.service"],
        "errors": {},
    }
