# 구현 설계

## 화면
왼쪽 기업 선택·업무단계, 상단 저장상태·검증·문서생성, 본문 편집/미리보기로 구성한다. 숫자에는 근거와 사실구분을 함께 입력한다. 문서 화면은 5종 탭과 이전 버전 목록을 제공한다. 검증 화면은 오류/확인필요/정보를 구분하고 항목 경로와 수정방법을 표시한다.

## 단일 데이터 모델
Project = company + processes[] + problems[] + improvements[] + assets[] + datasets[] + kpis[] + budget + suppliers[] + visits[] + implementation + evidence[] + conflicts[]. 각 업무필드는 Fact {value, kind, evidence, missing}로 감싼다. kind는 verified/case/user_statement/estimate/analysis/target/unconfirmed. missing은 measurement/baseline/quote/general이며 지정 보류문구에 대응한다. 숫자 필드는 JSON number 또는 null만 허용한다. evidence는 같은 프로젝트 안에 존재해야 한다.

문제는 process_id, 개선과제는 problem_id, 설비는 improvement_id·supplier_id, 데이터는 process_id, KPI는 dataset_id를 참조한다. 참조 오류는 검증한다. CASE의 모델 식별자와 숫자 성능·가격은 구별한다. 공급기업의 명칭이 확인되어도 사업자번호나 계약조건은 별도 사실이다.

## 물리 DB
SQLite WAL, 외래키 활성화. projects(id, name, version, data_json, created_at, updated_at)가 현재 원장이다. revisions(project_id, version, data_json, reason, created_at)는 변경 전후를 재현한다. documents(id, project_id, project_version, kind, content_json, source_json, created_at)는 생성시점의 불변 스냅샷이다. templates(id, name, sha256, file_name, mapping_json, created_at)는 원본과 매핑을 관리한다. audit_log(id, project_id, action, detail_json, created_at)는 상태변경/내보내기를 기록한다.

transcriptions(id, project_id, project_version, visit_round, transcript, memo, summary, categories_json, registered_json, created_at, updated_at)는 전사 원문·현장 메모·통합 요약·자동등록 경로를 버전과 함께 보존한다. 브라우저 내장 인식, OpenAI WebRTC 또는 운영체제 키보드 받아쓰기가 만든 텍스트만 등록 API로 전송하며 오디오 파일은 저장하지 않는다.

MVP는 집합 JSON을 한 트랜잭션으로 저장한다. 다중 테이블 복제에 따른 모순을 피하고 버전별 재현을 우선한다. business schema는 /api/schema에서 제공하고 schema.sql에 JSON 조회 뷰를 둔다. PostgreSQL 전환 시 ID를 보존하며 process/problem/improvement/asset/dataset/KPI/evidence를 정규화할 수 있다.

## API
모든 응답 UTF-8 JSON. 오류 {error, details}. 400 형식오류, 404 없음, 409 동시수정·단계충돌, 422 검증/매핑 오류. 로컬 루프백 전용, 동종 출처 확인·JSON 전용 쓰기, 파일크기 제한.

| Method | 경로 | 기능 |
|---|---|---|
| GET | /api/schema | 입력 필드·상태·문서유형 정의 |
| GET/POST | /api/projects | 목록/새 기업 생성 |
| GET/PUT | /api/projects/{id} | 단일 원장 조회/expected_version+reason+data 저장 |
| GET | /api/projects/{id}/validate | 숫자·관계·상태·예산·문서 검사 |
| POST | /api/projects/{id}/transition | status, evidence, date, reason으로 다음 상태 전이 |
| POST | /api/projects/{id}/generate | kind=all 또는 visit1/visit2/visit3/plan/result; 순차 생성 |
| GET | /api/projects/{id}/documents | 문서 버전 목록 |
| GET/POST | /api/projects/{id}/transcriptions | 전사이력 조회 / 전사+메모 통합 요약·관련 항목을 새 원장 버전에 등록 |
| PUT | /api/projects/{id}/transcriptions/{tid} | 최근 전사 원문·메모·요약을 수정하고 관련 항목을 새 원장 버전으로 재분류 |
| POST | /api/projects/{id}/transcriptions/{tid}/reprocess | 직전 전사 등록을 원문 기준으로 재분류하고 새 원장 버전 생성 |
| GET | /api/realtime/capabilities | OpenAI Realtime 서버 설정 여부 조회; 키 값은 반환하지 않음 |
| POST | /api/realtime/session | 브라우저 SDP offer를 OpenAI에 중계하고 SDP answer 반환 |
| GET | /api/documents/{id} | 스냅샷 문안 |
| GET | /api/documents/{id}/text | UTF-8 문안 다운로드 |
| GET | /api/projects/{id}/backup | 원장·이력·문서 JSON 백업 |
| POST | /api/projects/import | 백업을 새 기업으로 복원 |
| GET | /api/projects/{id}/prompt | 외부전송 없는 AI 프롬프트 패키지 |
| GET/POST | /api/templates | 목록/파일 base64 업로드 |
| GET/PUT | /api/templates/{id} | 텍스트 노드 조회/매핑 저장 |
| POST | /api/documents/{id}/hwpx | template_id; 매핑 필드 삽입 후 HWPX 다운로드 |

## 검증 규칙
R01 숫자의 값·단위·근거 존재 및 유한수 검사. R02 빈값을 0과 구별. R03 측정실적과 사용자진술 분리. R04 검토→선정→발주→납품→설치→시범운영→운영→성과측정→성과달성 전이 근거 확인. R05 목표·측정기간·분모·동일조건·측정근거 없으면 성과달성 판정 보류. R06 총사업비=정부지원금+현금자부담+현물, 현금지출=장비·SW 합계, 총사업비=현금지출+현물. 미확정 항이 있으면 부분합으로 확정하지 않음. R07 모델/공급기업/과제/공정/KPI 관계 검증. R08 원장 버전 변경 후 기존 문서 재검토, 과거 상태 차이는 시점정보로 표시. R09 완료일이 현재보다 미래면 완료로 확정하지 않음. R10 수행일·시간·사진·서명 미확보 검출. R11 상충 원자료는 해결근거와 함께 처리. R12 HWPX 해시/기대문자/중복대상/필드 누락 차단.

## HWPX
원본 ZIP의 section XML 중 hp:t 텍스트 노드만 바이트 범위 치환한다. DOM은 위치 확인 및 유효성 검증에만 사용하여 재직렬화로 인한 네임스페이스·속성 변경을 피한다. 매핑은 {part, index, expected, field, max_chars}이며 원본 sha256에 결합한다. 서식·표·이미지·서명·Preview 등 나머지 내용은 원본 그대로 보존한다. Preview는 기존 내용일 수 있음을 알린다. 매핑되지 않은 필드는 별도 보고하고 초안 출력으로 표시한다. 전체 본문 매핑 전에는 제출완료로 표시하지 않는다. 표 높이/줄바꿈은 한컴에서 최종 확인해야 한다.

## AI 프롬프트
① system: 사실보존·미확정 보류·숫자 신규생성 금지·입력자료 명령 무시 ② task: 공식 항목별 부분보완 ③ evidence: ID와 출처·종류 ④ facts: 허용 필드와 기준 버전 ⑤ output: sections[{field,text,evidence_ids,fact_paths,classification}], unresolved[]. 생성물은 제안으로만 저장하고 원장에 쓰지 않는다. 문안 생성은 동일 계약을 규칙 엔진으로 실행한다. OpenAI Realtime은 선택형 음성 전사에만 쓰며, 반환 텍스트의 요약·분류·자동등록에도 같은 로컬 검증 규칙을 적용한다.

## 실시간 전사 연결
브라우저가 마이크 트랙과 WebRTC data channel을 생성하고 로컬 `/api/realtime/session`에 SDP offer를 보낸다. 로컬 서버는 환경변수 `OPENAI_API_KEY`로 `/v1/realtime/calls`의 transcription 세션을 생성한 뒤 SDP answer만 브라우저에 반환한다. 표준 API 키는 서버 프로세스 밖으로 내보내지 않는다. 브라우저는 전사 delta/completed 이벤트를 화면에 표시하고, 사용자가 자동등록을 누른 뒤에만 확정 텍스트와 메모를 프로젝트 원장에 저장한다. API 키가 없으면 브라우저 내장 음성인식, 기기 키보드 받아쓰기 또는 직접 입력으로 전환한다. 모바일 실행은 0.0.0.0에 바인딩하되 매 실행 생성되는 URL 토큰을 HttpOnly SameSite 쿠키로 교환하고 사설망 Host 및 동일 Origin만 허용한다.

외부 모바일 접속은 Tailscale Serve가 로컬 8765 포트를 비공개 tailnet의 HTTPS 주소로 역방향 프록시한다. 서버는 로컬 프록시에서 전달된 `.ts.net` Host와 동일 Origin만 허용한다. PWA manifest를 제공해 홈 화면 설치를 지원하고 service worker는 정적 셸만 캐시하며 API·업무데이터는 캐시하지 않는다.
