# Docker 배포

구성: 브라우저 → Nginx(React, 8080) → FastAPI(8000, 내부) → 기존 AWS MySQL(예: RDS).
Docker는 frontend와 backend 두 서비스만 실행합니다.
Docker Engine 및 Compose 플러그인이 설치된 Linux 서버 또는 Docker Desktop의 Linux 컨테이너 모드를 사용합니다.

## 환경 설정

프로젝트 루트에 `.env.example`을 참고해 `.env`를 작성합니다. 기존 파일이 있으면 필요한 변수만 보완합니다.
`server/.env`는 이미지에 포함되지 않으므로 필요한 설정을 루트 `.env`로 옮겨야 합니다.

- `DB_HOST`: 기존 AWS MySQL 엔드포인트(프로토콜과 포트 제외).
- `DB_PORT`: 기존 DB 포트, 기본 3306.
- `DB_USER`, `DB_NAME`, `DB_PASSWORD`: 기존 DB 계정, DB 이름, 비밀번호.
- `JWT_SECRET_KEY`: 충분히 긴 임의 문자열.
- `HENRIK_API_KEY`, `HENRIK_ML_API_KEY`: 기존 키 변수 유지.
- `ANTHROPIC_API_KEY`: AI 리포트 사용 시 설정.
- `WEB_PORT`: 기본 8080. `FRONT_ORIGINS`: 접속 주소(예: `http://서버IP:8080`).

Compose가 루트 `.env`의 DB 접속 정보를 backend에 전달합니다. `MYSQL_ROOT_PASSWORD`는 필요하지 않습니다.
비밀번호에 `$`가 있으면 `.env`에서 값을 작은따옴표로 감싸 Compose 보간을 방지하세요.
API 키와 비밀번호는 이미지나 프론트엔드 빌드에 포함되지 않습니다.

## 실행

프로젝트 루트에서:

```sh
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend
```

`http://서버IP:8080`에 접속합니다. 서버 방화벽에서 웹 포트를 허용하세요.
공개 서비스의 로그인은 도메인과 HTTPS를 연결한 뒤 사용합니다. 현재 구성은 HTTP이며,
HTTPS는 앞단 로드밸런서/리버스 프록시에서 설정해야 합니다.
React의 직접 URL 접근과 새로고침을 지원하며 `/api`는 같은 출처로 전달됩니다.
예측 대기를 고려해 Nginx 응답 대기 시간을 300초로 설정했습니다.

## DB와 기존 데이터

기존 AWS DB의 테이블과 회원·경기·예측 데이터를 그대로 사용합니다. 별도 데이터 이관은 필요하지 않습니다.
Compose는 DB 생성·초기화·마이그레이션 SQL을 실행하지 않습니다.
앱을 사용하면서 발생하는 회원가입·예측 저장 등의 쓰기는 연결된 AWS DB에 반영됩니다.
컨테이너를 종료하거나 다시 빌드해도 AWS DB는 유지됩니다.

배포 서버에서 DB 엔드포인트와 포트에 접근할 수 있어야 합니다.
RDS 보안 그룹에는 배포 서버로부터의 DB 포트 접근을 허용하고,
비공개 DB는 해당 VPC로 연결 가능한 네트워크에서 실행하세요.
DB가 TLS 연결을 강제한다면 해당 DB의 인증서 및 연결 요구사항에 맞춘 별도 설정이 필요합니다.
기존 로컬 MySQL 컨테이너나 볼륨이 있다면 이 변경으로 자동 삭제되지 않습니다.

## 업데이트와 점검

```sh
docker compose up -d --build
docker compose logs --tail=100 backend frontend
```

백엔드는 API 제한기와 메모리 캐시를 공유하도록 worker 1개를 사용합니다.
worker/컨테이너 수를 늘리려면 제한기와 캐시의 외부 공유를 먼저 구현해야 합니다.
`/health`는 프로세스 생존 여부만 확인하며 DB/API 정상 동작을 보장하지 않습니다.
로그인, 팀 조회, 실제 예측, AI 리포트는 배포 후 유효한 키로 별도 확인합니다.
모델 파일은 이미지에 포함되며 기존 requirements의 scikit-learn 버전을 유지합니다.
모델 로딩 오류 시 학습 환경과 라이브러리 버전을 일치시켜야 합니다.

외부 API를 호출하지 않는 컨테이너 점검(프로젝트 루트에서 실행):

```sh
docker compose cp deploy/check_runtime.py backend:/tmp/check_runtime.py
docker compose exec -e PYTHONPATH=/app/server backend python /tmp/check_runtime.py
```

점검은 모델의 합성 입력 추론 및 DB 읽기만 수행합니다. 실서비스 예측 정확도 검증은 아닙니다.

설정 참고: [Docker Compose 서비스](https://docs.docker.com/reference/compose-file/services/),
[Nginx 프록시](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
