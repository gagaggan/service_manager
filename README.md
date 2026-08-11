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

- `0.1.1`: Docker 컨테이너와 systemd 서비스를 별도 섹션으로 표시
- `0.1.0`: 초기 서비스 조회 및 재시작 기능

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
systemd 항목은 FlaskFarm이 호스트의 systemd에 직접 접근할 수 없으므로
별도 호스트 에이전트가 필요합니다.

## 테스트용 실행

```bash
python -m pytest
```
