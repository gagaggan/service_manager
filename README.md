# FlaskFarm Service Manager

FlaskFarm에서 Docker 컨테이너와 systemd 서비스를 한 화면에서 확인하고,
허용된 대상만 재시작하기 위한 플러그인입니다.

## 보안

이 플러그인은 Docker 데몬과 systemd를 제어할 수 있으므로 관리자 전용으로
운영해야 합니다. `config.yaml`의 allowlist에 등록된 대상만 동작하도록
설계되어 있습니다. Docker 소켓을 외부 TCP에 노출하지 마세요.

## 개발 상태

현재 버전은 핵심 서비스 조회/재시작 로직과 Flask 테스트용 Blueprint를
포함한 초기 골격입니다. 실제 FlaskFarm 메뉴 등록은 설치된 FlaskFarm
버전에 맞춰 `__init__.py`의 어댑터를 연결해야 합니다.

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

## 테스트용 실행

```bash
python -m pytest
```

