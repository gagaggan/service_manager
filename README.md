# FlaskFarm Service Manager

FlaskFarm에서 Docker 컨테이너와 systemd 서비스를 확인하고 재시작하는
관리 플러그인입니다.

## 설치

FlaskFarm의 플러그인 설치 화면에 다음 저장소 주소를 입력합니다.

```text
https://github.com/gagaggan/service_manager
```

관리 대상은 플러그인의 `허용 목록 설정` 화면에서 FlaskFarm DB로 관리합니다.

## 호스트 systemd 에이전트

FlaskFarm이 Docker 컨테이너에서 실행되므로 systemd 제어를 위해 호스트
에이전트를 설치해야 합니다.

```bash
sudo install -d /usr/local/lib/service-manager-agent /etc/service-manager-agent
sudo install -m 755 host-agent/service_manager_agent.py /usr/local/lib/service-manager-agent/
sudo install -m 644 host-agent/service-manager-agent.service /etc/systemd/system/
sudo install -m 640 host-agent/services.json.example /etc/service-manager-agent/services.json
sudo groupadd --system service-manager 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl enable --now service-manager-agent
```

`services.json`에는 허용할 `.service`만 등록합니다. Codex 같은 사용자
서비스는 `scope: user`와 사용자명을 함께 지정합니다.

## 보안

Docker socket과 systemd 에이전트는 강력한 호스트 제어 권한을 가집니다.
FlaskFarm은 관리자 전용으로 운영하고, Docker socket을 외부 TCP에 노출하지
마세요. 에이전트는 allowlist에 등록된 서비스만 처리합니다.
