#!/bin/bash

# MCP Atlassian Container Apps 배포 스크립트
# Korea Central 리전, mcp-test 환경에 배포

set -e

# 환경 변수 설정
SUBSCRIPTION_ID="sub-az01-co001501-sbox-poc-131"
RESOURCE_GROUP="rg-az01-co001501-sbox-poc-131"
LOCATION="koreacentral"
CONTAINER_APPS_ENVIRONMENT="mcp-test"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Azure CLI 로그인 확인
check_azure_login() {
    log_info "Azure CLI 로그인 상태 확인 중..."
    if ! az account show > /dev/null 2>&1; then
        log_error "Azure CLI에 로그인되어 있지 않습니다. 'az login'을 실행해주세요."
        exit 1
    fi
    
    # 구독 설정
    log_info "구독을 설정합니다: $SUBSCRIPTION_ID"
    az account set --subscription $SUBSCRIPTION_ID
    log_success "구독이 설정되었습니다."
}

# Container Apps 환경 확인
check_container_apps_environment() {
    log_info "Container Apps 환경 확인 중: $CONTAINER_APPS_ENVIRONMENT"
    
    if ! az containerapp env show \
        --name $CONTAINER_APPS_ENVIRONMENT \
        --resource-group $RESOURCE_GROUP > /dev/null 2>&1; then
        log_error "Container Apps 환경 '$CONTAINER_APPS_ENVIRONMENT'이 존재하지 않습니다."
        log_info "다음 명령으로 환경을 생성할 수 있습니다:"
        echo "az containerapp env create \\"
        echo "  --name $CONTAINER_APPS_ENVIRONMENT \\"
        echo "  --resource-group $RESOURCE_GROUP \\"
        echo "  --location $LOCATION"
        exit 1
    fi
    
    log_success "Container Apps 환경이 확인되었습니다."
}

# Jira 서비스 배포
deploy_jira_service() {
    log_info "Jira MCP 서비스 배포 중..."
    
    # Jira URL 입력 받기
    read -p "Jira URL을 입력하세요 (예: https://your-domain.atlassian.net): " JIRA_URL
    
    if [ -z "$JIRA_URL" ]; then
        log_error "Jira URL이 입력되지 않았습니다."
        exit 1
    fi
    
    # Container Apps 배포
    az containerapp create \
        --name mcp-jira-service \
        --resource-group $RESOURCE_GROUP \
        --environment $CONTAINER_APPS_ENVIRONMENT \
        --image ujeongeom/mcp-atlassian-jira:ENV_add \
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
            JIRA_URL=secretref:jira-url \
        --secrets \
            jira-url=$JIRA_URL \
        --cpu 0.5 \
        --memory 1Gi \
        --min-replicas 1 \
        --max-replicas 10 \
        --query properties.configuration.ingress.fqdn \
        --output tsv
    
    log_success "Jira MCP 서비스가 배포되었습니다."
}

# Confluence 서비스 배포
deploy_confluence_service() {
    log_info "Confluence MCP 서비스 배포 중..."
    
    # Confluence URL 입력 받기
    read -p "Confluence URL을 입력하세요 (예: https://your-domain.atlassian.net/wiki): " CONFLUENCE_URL
    
    if [ -z "$CONFLUENCE_URL" ]; then
        log_error "Confluence URL이 입력되지 않았습니다."
        exit 1
    fi
    
    # Container Apps 배포
    az containerapp create \
        --name mcp-confluence-service \
        --resource-group $RESOURCE_GROUP \
        --environment $CONTAINER_APPS_ENVIRONMENT \
        --image ujeongeom/mcp-atlassian-confluence:ENV_add \
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
            CONFLUENCE_URL=secretref:confluence-url \
        --secrets \
            confluence-url=$CONFLUENCE_URL \
        --cpu 0.5 \
        --memory 1Gi \
        --min-replicas 1 \
        --max-replicas 10 \
        --query properties.configuration.ingress.fqdn \
        --output tsv
    
    log_success "Confluence MCP 서비스가 배포되었습니다."
}

# 서비스 상태 확인
check_service_status() {
    log_info "배포된 서비스 상태 확인 중..."
    
    echo ""
    echo "=== Jira MCP 서비스 ==="
    az containerapp show \
        --name mcp-jira-service \
        --resource-group $RESOURCE_GROUP \
        --query "{Name:name, Status:properties.runningStatus, URL:properties.configuration.ingress.fqdn}" \
        --output table
    
    echo ""
    echo "=== Confluence MCP 서비스 ==="
    az containerapp show \
        --name mcp-confluence-service \
        --resource-group $RESOURCE_GROUP \
        --query "{Name:name, Status:properties.runningStatus, URL:properties.configuration.ingress.fqdn}" \
        --output table
}

# 메인 함수
main() {
    echo "=========================================="
    echo "MCP Atlassian Container Apps 배포 스크립트"
    echo "=========================================="
    echo ""
    
    # 사전 조건 확인
    check_azure_login
    check_container_apps_environment
    
    echo ""
    echo "배포할 서비스를 선택하세요:"
    echo "1) Jira MCP 서비스만"
    echo "2) Confluence MCP 서비스만"
    echo "3) 둘 다"
    echo "4) 취소"
    echo ""
    read -p "선택 (1-4): " choice
    
    case $choice in
        1)
            deploy_jira_service
            ;;
        2)
            deploy_confluence_service
            ;;
        3)
            deploy_jira_service
            echo ""
            deploy_confluence_service
            ;;
        4)
            log_info "배포가 취소되었습니다."
            exit 0
            ;;
        *)
            log_error "잘못된 선택입니다."
            exit 1
            ;;
    esac
    
    echo ""
    check_service_status
    
    echo ""
    log_success "배포가 완료되었습니다!"
    echo ""
    echo "다음 단계:"
    echo "1. IDE에서 MCP 서버를 구성하세요"
    echo "2. 사용자별 인증 토큰을 설정하세요"
    echo "3. 헬스체크 엔드포인트로 서비스 상태를 확인하세요"
    echo ""
    echo "예시 IDE 설정:"
    echo '{'
    echo '  "mcpServers": {'
    echo '    "mcp-jira": {'
    echo '      "url": "https://mcp-jira-service.koreacentral.azurecontainerapps.io/mcp"'
    echo '    },'
    echo '    "mcp-confluence": {'
    echo '      "url": "https://mcp-confluence-service.koreacentral.azurecontainerapps.io/mcp"'
    echo '    }'
    echo '  }'
    echo '}'
}

# 스크립트 실행
main "$@" 