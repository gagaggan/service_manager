# FlaskFarm Service Manager

FlaskFarm에서 Docker 컨테이너와 systemd 서비스를 한 화면에서 확인하고,
허용된 대상만 재시작하기 위한 플러그인입니다.

## 보안

이 플러그인은 Docker 데몬과 systemd를 제어할 수 있으므로 관리자 전용으로
운영해야 합니다. `config.yaml`의 allowlist에 등록된 대상만 동작하도록
설계되어 있습니다. Docker 소켓을 외부 TCP에 노출하지 마세요.

## FlaskFarm 설치

FlaskFarm 관리자 화면의 플러그인 설치 메뉴에 이 저장소 URL을 입력합니다.

```text
https://github.com/gagaggan/service_manager
```

이 플러그인은 FlaskFarm 공식 `setup.py` / `PluginModuleBase` 규격을 따릅니다.

## 변경 이력

- `0.2.0`: 제한된 호스트 systemd 에이전트 연결 추가
- `0.1.4`: 기존 `docker run` 설정을 재사용 가능한 Docker Compose 파일로 추가
- `0.1.3`: FlaskFarm 공통 레이아웃을 적용해 기존 메뉴·로그 화면과 통합
- `0.1.2`: systemd 미연결 환경에서 오류 화면 대신 unavailable 상태 표시
- `0.1.1`: Docker 컨테이너와 systemd 서비스를 별도 섹션으로 표시
- `0.1.0`: 초기 서비스 조회 및 재시작 기능

## Docker Compose 실행

저장소의 `docker-compose.yml`은 기존 `ff` 컨테이너 실행 옵션을 옮긴 파일입니다.

```bash
docker compose up -d
```

기존에 같은 이름의 컨테이너가 실행 중이면 먼저 중지/삭제해야 합니다.

```bash
docker stop ff
docker rm ff
docker compose up -d
```

## 설정 예시

```yaml
docker:
  enabled: true
  containers:
    - codex
    - plex
systemd:
  enabled: true
  services:
    - nginx.service
    - my-app.service
```

FlaskFarm이 Docker 컨테이너 안에서 실행된다면 FlaskFarm 컨테이너에 Docker
소켓을 연결해야 합니다. Docker Compose에서는 다음을 추가합니다.

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

Docker 소켓이 연결되지 않으면 Docker 항목은 `unavailable`로 표시됩니다.

### systemd 호스트 에이전트

호스트에서 다음처럼 설치합니다.

```bash
sudo install -d /usr/local/lib/service-manager-agent /etc/service-manager-agent
sudo install -m 755 host-agent/service_manager_agent.py /usr/local/lib/service-manager-agent/
sudo install -m 644 host-agent/service-manager-agent.service /etc/systemd/system/
sudo install -m 640 host-agent/services.json.example /etc/service-manager-agent/services.json
sudo groupadd --system service-manager 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl enable --now service-manager-agent
```

`services.json`에는 실제로 허용할 `.service`만 남깁니다. 이후 `docker compose up -d`
로 FlaskFarm을 재생성하면 `/run/service-manager-agent.sock`을 통해 호스트
systemd 상태 조회와 재시작을 사용할 수 있습니다.

## 테스트용 실행

```bash
python -m pytest
```
