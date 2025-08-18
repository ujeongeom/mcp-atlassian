# MCP Atlassian Container Apps 배포 가이드

이 가이드는 MCP Atlassian을 Azure Container Apps에 Jira와 Confluence를 별도의 서비스로 배포하는 방법을 설명합니다.

## 개요

기존의 통합 MCP 서버를 Jira와 Confluence로 분리하여 각각 독립적인 Container Apps 서비스로 배포합니다. 이를 통해:

- **독립적 스케일링**: 각 서비스를 독립적으로 스케일링 가능
- **장애 격리**: 한 서비스의 장애가 다른 서비스에 영향 없음
- **리소스 최적화**: 각 서비스에 필요한 리소스만 할당
- **보안 격리**: 각 서비스별로 다른 보안 정책 적용 가능

## 사전 요구사항

1. **Azure CLI** 설치 및 로그인
2. **Container Apps 환경** 생성 (`mcp-test`)
3. **Atlassian Cloud 계정** 및 API 토큰
4. **Docker 이미지** 빌드 및 푸시

## 아키텍처

```
┌─────────────────┐    ┌─────────────────────┐
│   IDE Client    │    │   IDE Client        │
│   (Jira)        │    │   (Confluence)      │
└─────────┬───────┘    └─────────┬───────────┘
          │                      │
          ▼                      ▼
┌─────────────────┐    ┌─────────────────────┐
│  Jira MCP       │    │  Confluence MCP     │
│  Service        │    │  Service            │
│  (Container     │    │  (Container         │
│   Apps)         │    │   Apps)             │
└─────────┬───────┘    └─────────┬───────────┘
│                      │
          ▼                      ▼
┌─────────────────┐    ┌─────────────────────┐
│   Jira Cloud    │    │   Confluence Cloud  │
│   API           │    │   API               │
└─────────────────┘    └─────────────────────┘
```

## 배포 단계

### 1. Docker 이미지 빌드

```bash
# Jira 전용 이미지 빌드
docker build -f Dockerfile.jira -t ghcr.io/sooperset/mcp-atlassian-jira:latest .

# Confluence 전용 이미지 빌드
docker build -f Dockerfile.confluence -t ghcr.io/sooperset/mcp-atlassian-confluence:latest .

# 이미지 푸시
docker push ghcr.io/sooperset/mcp-atlassian-jira:latest
docker push ghcr.io/sooperset/mcp-atlassian-confluence:latest
```

### 2. 자동 배포 스크립트 실행

```bash
# 배포 스크립트 실행
./deploy-container-apps.sh
```

스크립트는 다음을 수행합니다:
- Azure CLI 로그인 상태 확인
- Container Apps 환경 확인
- Jira/Confluence URL 입력 받기
- Container Apps 서비스 배포
- 배포 상태 확인

### 3. 수동 배포 (선택사항)

#### Jira 서비스 배포

```bash
az containerapp create \
  --name mcp-jira-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --environment mcp-test \
  --image ghcr.io/sooperset/mcp-atlassian-jira:latest \
  --target-port 9000 \
  --ingress external \
  --transport http \
  --env-vars \
    TRANSPORT=streamable-http \
    PORT=9000 \
    HOST=0.0.0.0 \
    STREAMABLE_HTTP_PATH=/mcp \
    MCP_LOGGING_STDOUT=true \
    MCP_VERBOSE=true \
  --secrets \
    jira-url=https://your-domain.atlassian.net \
  --env-vars \
    JIRA_URL=secretref:jira-url \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 10
```

#### Confluence 서비스 배포

```bash
az containerapp create \
  --name mcp-confluence-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --environment mcp-test \
  --image ghcr.io/sooperset/mcp-atlassian-confluence:latest \
  --target-port 9000 \
  --ingress external \
  --transport http \
  --env-vars \
    TRANSPORT=streamable-http \
    PORT=9000 \
    HOST=0.0.0.0 \
    STREAMABLE_HTTP_PATH=/mcp \
    MCP_LOGGING_STDOUT=true \
    MCP_VERBOSE=true \
  --secrets \
    confluence-url=https://your-domain.atlassian.net/wiki \
  --env-vars \
    CONFLUENCE_URL=secretref:confluence-url \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 10
```

## 클라이언트 설정

### IDE 설정 예시

`client-config-example.json` 파일을 참조하여 IDE에서 MCP 서버를 구성하세요:

```json
{
  "mcpServers": {
    "mcp-jira": {
      "url": "https://mcp-jira-service.koreacentral.azurecontainerapps.io/mcp",
      "headers": {
        "Authorization": "Bearer ${JIRA_TOKEN}",
        "X-User-Email": "${USER_EMAIL}"
      }
    },
    "mcp-confluence": {
      "url": "https://mcp-confluence-service.koreacentral.azurecontainerapps.io/mcp",
      "headers": {
        "Authorization": "Bearer ${CONFLUENCE_TOKEN}",
        "X-User-Email": "${USER_EMAIL}"
      }
    }
  }
}
```

### 환경 변수 설정

```bash
# Jira 토큰 설정
export JIRA_TOKEN="your-jira-api-token"

# Confluence 토큰 설정
export CONFLUENCE_TOKEN="your-confluence-api-token"

# 사용자 이메일 설정
export USER_EMAIL="your-email@domain.com"
```

## 모니터링 및 관리

### 서비스 상태 확인

```bash
# Jira 서비스 상태
az containerapp show \
  --name mcp-jira-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --query "{Name:name, Status:properties.runningStatus, URL:properties.configuration.ingress.fqdn}"

# Confluence 서비스 상태
az containerapp show \
  --name mcp-confluence-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --query "{Name:name, Status:properties.runningStatus, URL:properties.configuration.ingress.fqdn}"
```

### 로그 확인

```bash
# Jira 서비스 로그
az containerapp logs show \
  --name mcp-jira-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --follow

# Confluence 서비스 로그
az containerapp logs show \
  --name mcp-confluence-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --follow
```

### 서비스 모니터링

Azure Container Apps는 자체적으로 컨테이너 상태 모니터링을 제공합니다:

- **자동 재시작**: 컨테이너가 비정상 종료될 경우 자동으로 재시작
- **상태 확인**: 컨테이너 프로세스 상태 모니터링
- **메트릭**: CPU, 메모리, 네트워크 사용량 추적
- **로그 수집**: 애플리케이션 로그 자동 수집 및 보관

## 스케일링

### 자동 스케일링 설정

```bash
# Jira 서비스 스케일링 규칙 설정
az containerapp revision set-mode \
  --name mcp-jira-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --mode multiple

# Confluence 서비스 스케일링 규칙 설정
az containerapp revision set-mode \
  --name mcp-confluence-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --mode multiple
```

### 수동 스케일링

```bash
# Jira 서비스 레플리카 수 조정
az containerapp replica count set \
  --name mcp-jira-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --replica-count 3

# Confluence 서비스 레플리카 수 조정
az containerapp replica count set \
  --name mcp-confluence-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --replica-count 2
```

## 문제 해결

### 일반적인 문제

1. **인증 실패**
   - API 토큰이 올바른지 확인
   - 사용자 이메일이 정확한지 확인
   - 토큰 권한이 충분한지 확인

2. **서비스 연결 실패**
   - Container Apps 서비스가 실행 중인지 확인
   - URL이 올바른지 확인
   - 네트워크 연결 상태 확인

3. **리소스 부족**
   - CPU/메모리 할당량 확인
   - 스케일링 설정 확인

### 로그 분석

```bash
# 상세 로그 확인
az containerapp logs show \
  --name mcp-jira-service \
  --resource-group rg-az01-co001501-sbox-poc-131 \
  --follow \
  --output table
```

## 보안 고려사항

1. **API 토큰 관리**
   - 토큰을 안전하게 저장
   - 정기적으로 토큰 갱신
   - 최소 권한 원칙 적용

2. **네트워크 보안**
   - HTTPS 사용
   - 적절한 방화벽 규칙 설정
   - VNet 통합 고려

3. **모니터링**
   - 로그 모니터링 설정
   - 알림 규칙 구성
   - 정기적인 보안 감사

## 비용 최적화

1. **리소스 할당**
   - 실제 사용량에 맞는 CPU/메모리 설정
   - 자동 스케일링 활용

2. **스케일링 정책**
   - 트래픽 패턴에 맞는 스케일링 규칙
   - 비용 효율적인 레플리카 수 설정

3. **예약 인스턴스**
   - 장기 사용 시 예약 인스턴스 고려
   - 비용 절약 계획 수립 