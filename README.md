# Smart_Coordi

스마트제조 지원사업 코디네이터 업무를 브라우저에서 관리하기 위한 웹앱입니다.

## 현재 구현
- 업체/프로젝트 등록·수정·삭제
- 사업자등록번호 및 전화번호 자동 구분기호
- 사업비 천 단위 표시 및 재원 합계 검증
- 현장방문 등록·수정·삭제
- 현장방문 화면 안에서 브라우저 녹음
- Chrome/Edge 실시간 보조 전사(지원 환경에서만)
- 녹음 종료 후 브라우저 로컬 Whisper 고정밀 전사(외부 API Key 불필요)
- 문제·원인·개선과제 CRUD
- KPI·H/W·S/W CRUD
- IndexedDB 업체별 데이터 저장
- JSON 전체 데이터 백업·복원
- PWA 기본 구조

## 데이터 저장 원칙
무료 GitHub Pages 버전은 별도 백엔드가 없으므로 업체 데이터는 사용 중인 브라우저의 IndexedDB에 저장됩니다. 실제 업체 정보와 녹음 파일은 GitHub 저장소에 자동 업로드되지 않습니다. 정기적으로 `백업·복원` 메뉴에서 JSON 백업을 보관하세요.

## 음성 전사
1. 녹음 시작/종료는 브라우저 MediaRecorder를 사용합니다.
2. Chrome/Edge에서 Web Speech Recognition을 사용할 수 있으면 녹음 중 보조 전사가 표시됩니다. 이 기능의 처리 방식은 브라우저 제공자 정책에 따라 달라질 수 있습니다.
3. 문서 작성용 최종 전사는 `로컬 Whisper 고정밀 전사`를 권장합니다. 모델은 최초 1회 다운로드되며 브라우저 캐시에 저장되고, API Key는 필요하지 않습니다.

## GitHub Pages
이 저장소를 Public으로 전환하거나 계정에서 Private Pages가 허용되는 경우 Settings → Pages에서 `Deploy from a branch` → `main` / `/ (root)`를 선택하면 됩니다.

## 개발 지침
`AGENTS.md`를 우선 확인하세요.
