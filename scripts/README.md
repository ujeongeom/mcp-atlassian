# MCP Atlassian 로그 분석 스크립트

이 디렉토리에는 MCP Atlassian 서버의 로그를 분석하고 파일로 추출하는 스크립트들이 포함되어 있습니다.

## log_analyzer.py

MCP Atlassian 서버의 로그를 분석하고 다양한 형식으로 내보내는 스크립트입니다.

### 기능

- **로그 파싱**: JSON Lines 형식의 로그 파일을 파싱
- **요약 분석**: 서비스별, 도구별 통계 및 성능 메트릭
- **필터링**: 서비스(jira/confluence) 또는 특정 도구별 필터링
- **다양한 출력 형식**: 요약, 요청-응답 쌍, 원시 로그

### 사용법

#### 기본 요약 분석
```bash
python3 scripts/log_analyzer.py --input log_file.jsonl --format summary
```

#### JSON 파일로 내보내기
```bash
python3 scripts/log_analyzer.py --input log_file.jsonl --format summary --output analysis.json
```

#### 요청-응답 쌍 분석
```bash
python3 scripts/log_analyzer.py --input log_file.jsonl --format pairs --output pairs.json
```

#### 특정 서비스 필터링
```bash
python3 scripts/log_analyzer.py --input log_file.jsonl --filter confluence --format summary
```

#### 특정 도구 필터링
```bash
python3 scripts/log_analyzer.py --input log_file.jsonl --tool get_page_children --format summary
```

### 출력 형식

#### 1. Summary 형식
```json
{
  "total_logs": 2,
  "requests": 1,
  "responses": 1,
  "errors": 0,
  "services": {
    "confluence": 2
  },
  "tools": {
    "get_page_children": 2
  },
  "performance_stats": {
    "avg_execution_time_ms": 605.77,
    "total_execution_time_ms": 605.77,
    "success_count": 1,
    "error_count": 0
  }
}
```

#### 2. Pairs 형식
요청과 응답을 매칭하여 쌍으로 제공합니다.

#### 3. Raw 형식
파싱된 원시 MCP 로그 데이터를 제공합니다.

### 로그 형식

MCP Atlassian 서버는 다음과 같은 형식으로 로그를 생성합니다:

```json
{
  "TimeStamp": "2025-08-13T23:30:57.9338803+00:00",
  "Log": "F INFO - mcp_atlassian.utils.decorators - MCP_REQUEST: {\"event\": \"MCP_REQUEST\", \"tool\": \"get_page_children\", \"service\": \"confluence\", \"request_id\": \"7\", ...}"
}
```

### 성능 메트릭

- **실행 시간**: 각 요청의 처리 시간 (밀리초)
- **메모리 사용량**: 요청 시작/종료 시 메모리 사용량
- **성공/실패율**: 요청 처리 성공 및 실패 통계

### 예시 출력

```
============================================================
MCP Atlassian 로그 분석 요약
============================================================
총 로그 수: 2
요청 수: 1
응답 수: 1
오류 수: 0

서비스별 통계:
  confluence: 2

도구별 통계:
  get_page_children: 2

성능 통계:
  평균 실행 시간: 605.77ms
  총 실행 시간: 605.77ms
  성공: 1
  오류: 0
```

## 로그 형식 개선 제안

현재 로그는 JSON Lines 형식으로 출력되어 터미널에서 읽기 어려울 수 있습니다. 
이 스크립트를 사용하면 구조화된 분석 결과를 얻을 수 있으며, 
추후 로그 형식을 개선할 때 고려할 수 있는 옵션들:

1. **Pretty Print**: 터미널에서 읽기 쉬운 형식
2. **CSV Export**: 스프레드시트 분석용
3. **Real-time Monitoring**: 실시간 로그 모니터링
4. **Log Rotation**: 로그 파일 자동 관리 