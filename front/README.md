# VALO-BRIEF Frontend

Vite + React 기반 프론트엔드입니다.

## 시작하기
```bash
npm install
npm run dev
```

## FastAPI 서버 연동
1. `.env.development`의 `VITE_API_BASE_URL`을 비워두면 모든 데이터가 `src/mocks/*.mock.js`에서 옵니다.
2. FastAPI 서버가 준비되면 `.env.development`에 서버 주소를 채우세요:
   ```
   VITE_API_BASE_URL=http://localhost:8000
   ```
3. `src/api/endpoints.js`에 정의된 경로에 맞춰 FastAPI 라우터를 구현하면 코드 수정 없이 바로 연동됩니다.
4. 서버 요청이 실패해도 자동으로 mock 데이터로 폴백되므로(`src/api/withFallback.js`), 백엔드를 부분적으로만 완성한 상태에서도 개발을 계속할 수 있습니다.

## 폴더 구조
- `src/api` — FastAPI 연동 레이어 (엔드포인트 정의, httpClient, mock 폴백)
- `src/mocks` — 목 데이터
- `src/assets` — 이미지 자산 (아래 "이미지 자산 넣는 법" 참고)
- `src/components` — 공용 컴포넌트 (여러 페이지에서 재사용)
- `src/pages` — 페이지별 컴포넌트
- `src/layouts` — 페이지 그룹별 공통 레이아웃 (헤더/푸터)
- `src/styles` — 디자인 토큰 + 도메인별로 분리된 CSS (아래 "스타일 구조" 참고)

## 스타일 구조 (CSS 분리)
하나의 거대한 CSS 파일 대신, 도메인별로 파일을 나눴습니다.

```
src/styles/
  tokens.css              # 색상/폰트 변수 (:root)
  reset.css                # 브라우저 기본 스타일 리셋
  index.css                 # 전체를 순서대로 import하는 진입점 (main.jsx가 이 파일만 import)
  layout/
    appShell.css, header.css, footer.css
  components/
    button.css, tabs.css, table.css, stat.css, match.css, map.css,
    analysis.css, aim.css, predict.css, aiReport.css, popup.css,
    playerList.css, auth.css, profile.css, misc.css
  pages/
    home.css
```
새 컴포넌트를 추가할 때는 어울리는 파일에 규칙을 더하거나, 새 파일을 만들고
`src/styles/index.css`에 `@import` 한 줄만 추가하면 됩니다.

> 더 강한 스코핑(컴포넌트별 CSS Modules)이 필요하면 각 `.css`를 `.module.css`로 바꾸고
> 컴포넌트에서 `import styles from './X.module.css'` 형태로 바꾸는 방법도 있습니다.
> 지금은 클래스명 기반 전역 스타일이라 코드량이 적고 Figma 마크업과의 대조가 쉬운 방식을 택했습니다.

## 이미지 자산 넣는 법
`src/assets/images/{폴더}/` 에 파일을 넣기만 하면 자동으로 인식됩니다. import 문을 따로 추가할 필요 없습니다.

```
src/assets/images/
  logo/      # 날개 모양 로고 (wing.svg)
  teams/     # 팀 로고, 파일명 = 팀 태그 (PHX.png, ASC.png)
  agents/    # 요원 초상화, 파일명 = 요원 이름 (제트.png, 레이나.png)
  weapons/   # 무기 아이콘, 파일명 = 영문 무기명 (Vandal.png, Phantom.png)
  maps/      # 맵 이미지, 파일명 = 맵 이름 (어센트.png, 바인드.png)
  hitbox/    # 히트박스 오버레이 (default.png)
  rating/    # 티어 아이콘 (radiant.png, division-2.png ...)
  icons/     # SNS 등 기타 아이콘
```
각 폴더 안의 `README.md`에 어떤 컴포넌트가 어떤 key를 쓰는지 정리해뒀습니다.
파일이 없으면 자동으로 점선 placeholder 박스가 표시되고, 파일을 넣는 순간 별도 코드 수정 없이 실제 이미지로 바뀝니다.
(내부적으로 `src/assets/index.js`의 `getAsset(folder, key)`가 처리합니다)

`@` 경로 별칭이 설정되어 있어서 어디서든 `import { getAsset } from '@/assets'` 형태로 쓸 수 있습니다.

## 참고
- 이미지 자산(팀 로고, 요원, 무기, 맵, 히트박스 등)은 전부 `EmptyImageBox` placeholder로 표시됩니다. 실제 이미지가 준비되면 `src="..."` prop만 넘기면 자동으로 `<img>`로 교체됩니다.
- 탭 상태는 URL 쿼리스트링(`?tab=...`)으로 관리해서 새로고침해도 유지됩니다.
