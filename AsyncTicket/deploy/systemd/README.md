# FastAPI systemd 서비스 등록

Amazon Linux 2023에서 Python 가상환경으로 앱을 직접 실행하는 예시다.
터미널 종료 후에도 실행을 유지하고, 부팅 시 앱을 시작하며 비정상 종료 시 재시작한다.
서버에서 확인한 사용자·경로·Uvicorn 명령을 바탕으로 작성했으며,
기존 EC2 서비스 파일을 그대로 추출한 복사본은 아니다.

## 적용 전 확인

- Python 3.13 이상과 uv가 설치돼 있어야 한다.
- 예시 사용자 `ec2-user`, 프로젝트 경로 `/home/ec2-user/asyncticket-demo/AsyncTicket`를 서버에 맞춘다.
- 프로젝트 폴더에서 `uv sync --frozen --no-dev`로 `.venv`를 준비한다.
- RDS·JWT 등 환경변수는 서버의 기존 방식 또는 프로젝트 `.env`로 제공한다.
  앱은 python-dotenv로 `.env`를 읽는다. 서비스 파일에 비밀번호·토큰을 넣지 않는다.
- `.env` 및 RDS CA 파일은 서버에 보관하고 Git에 올리지 않는다.
  기존 RDS TLS 설정과 인증서 경로를 보존한다.
- `127.0.0.1:8000`은 서버 내부 접속용이다. 외부 HTTP·HTTPS는 Nginx가 전달한다.
- 이 서비스는 Docker 실행용이 아니다. Docker 전환 시 같은 호스트 포트를 두 실행 방식이
  동시에 사용하지 않도록 별도로 전환해야 한다.

## 기존 서버

이미 `asyncticket-demo.service`가 실행 중이면 새로 설치할 필요 없다.
현재 설정을 확인하고 필요한 차이만 검토한다. 출력에 민감한 환경변수가 있을 수 있으므로 공개 공유하지 않는다.

```bash
sudo systemctl cat asyncticket-demo.service
systemctl is-active asyncticket-demo.service
systemctl is-enabled asyncticket-demo.service
```

이 예시를 추가하는 PR은 서버의 서비스 설정을 변경하지 않는다.
`asyncticket-edge.service`, Nginx 및 인증서 갱신 서비스도 변경하지 않는다.

## 새 서버에 설치

아래 명령은 `AsyncTicket` 폴더에서 실행한다.
사용자·경로·환경변수가 준비된 경우에만 실행한다.
기존 서비스 파일이 있으면 메시지만 출력하고 설치·활성화 명령은 실행하지 않는다.
각 검사가 성공해야 다음 명령을 실행한다.

```bash
if sudo test -e /etc/systemd/system/asyncticket-demo.service; then
    echo '기존 파일 있음: 아래 설치는 실행하지 않았습니다. 먼저 기존 설정을 비교하세요.'
else
    sudo cp --no-clobber deploy/systemd/asyncticket-demo.service /etc/systemd/system/asyncticket-demo.service &&
    sudo systemd-analyze verify /etc/systemd/system/asyncticket-demo.service &&
    sudo systemctl daemon-reload &&
    sudo systemctl enable --now asyncticket-demo.service
fi
```

## 상태 확인과 코드 갱신

```bash
systemctl is-enabled asyncticket-demo.service
systemctl is-active asyncticket-demo.service
curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8000/docs
sudo journalctl -u asyncticket-demo.service -n 50 --no-pager
```

`enabled`는 부팅 시 시작 설정, `active`는 현재 실행 상태다.
실제 재부팅 후 가동 성공이나 모든 API·DB 기능 정상까지 증명하는 것은 아니다.
로그에는 민감정보가 포함될 수 있으므로 공개 공유 전에 확인한다.

머지된 팀 코드를 반영하고 의존성 설치가 성공한 뒤 앱 서비스만 재시작한다.

```bash
uv sync --frozen --no-dev
sudo systemctl restart asyncticket-demo.service
```

재시작 후 상태와 응답을 다시 확인한다. 기존 실행을 nohup 등으로 중복 시작하지 않는다.

참고: https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
