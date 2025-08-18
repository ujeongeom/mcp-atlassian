#!/usr/bin/env python3
"""
MCP Atlassian 로그 분석 및 파일 추출 스크립트

사용법:
    python scripts/log_analyzer.py --input log_file.txt --output analysis.json
    python scripts/log_analyzer.py --input log_file.txt --format summary
    python scripts/log_analyzer.py --input log_file.txt --filter confluence
"""

import json
import argparse
import sys
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict


class LogAnalyzer:
    def __init__(self):
        self.logs = []
        self.requests = {}
        self.responses = {}
        self.errors = []
        
    def parse_log_file(self, filename: str) -> None:
        """로그 파일을 파싱합니다."""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                        
                    try:
                        # JSON Lines 형식 파싱
                        log_entry = json.loads(line)
                        
                        # TimeStamp와 Log 필드를 가진 형식인지 확인
                        if 'TimeStamp' in log_entry and 'Log' in log_entry:
                            # Log 필드에서 MCP 로그 추출
                            log_content = log_entry['Log']
                            timestamp = log_entry['TimeStamp']
                            
                            # MCP_REQUEST, MCP_RESPONSE, MCP_ERROR 패턴 찾기
                            mcp_patterns = [
                                r'MCP_REQUEST: ({.*})',
                                r'MCP_RESPONSE: ({.*})',
                                r'MCP_ERROR: ({.*})'
                            ]
                            
                            for pattern in mcp_patterns:
                                match = re.search(pattern, log_content)
                                if match:
                                    try:
                                        mcp_data = json.loads(match.group(1))
                                        mcp_data['original_timestamp'] = timestamp
                                        self.logs.append(mcp_data)
                                        
                                        # 이벤트 타입별로 분류
                                        event_type = mcp_data.get('event', '')
                                        if event_type == 'MCP_REQUEST':
                                            request_id = mcp_data.get('request_id')
                                            if request_id:
                                                self.requests[request_id] = mcp_data
                                        elif event_type == 'MCP_RESPONSE':
                                            request_id = mcp_data.get('request_id')
                                            if request_id:
                                                self.responses[request_id] = mcp_data
                                        elif event_type == 'MCP_ERROR':
                                            self.errors.append(mcp_data)
                                        break
                                    except json.JSONDecodeError:
                                        print(f"Warning: MCP JSON 파싱 오류 (라인 {line_num})")
                                        continue
                        else:
                            # 직접 MCP 로그인 경우
                            self.logs.append(log_entry)
                            
                                                    # 이벤트 타입별로 분류
                        event_type = log_entry.get('event', '')
                        if event_type == 'MCP_REQUEST':
                            request_id = log_entry.get('request_id')
                            if request_id:
                                self.requests[request_id] = log_entry
                        elif event_type == 'MCP_RESPONSE':
                            request_id = log_entry.get('request_id')
                            if request_id:
                                self.responses[request_id] = log_entry
                        elif event_type == 'MCP_ERROR':
                            self.errors.append(log_entry)
                        elif event_type in ['MCP_SYSTEM_EVENT', 'MCP_AUTH_EVENT', 'MCP_BUSINESS_EVENT']:
                            # 새로운 이벤트 타입들도 로그에 추가
                            self.logs.append(log_entry)
                            
                    except json.JSONDecodeError as e:
                        print(f"Warning: JSON 파싱 오류 (라인 {line_num}): {e}")
                        continue
                        
        except FileNotFoundError:
            print(f"Error: 파일을 찾을 수 없습니다: {filename}")
            sys.exit(1)
        except Exception as e:
            print(f"Error: 파일 읽기 오류: {e}")
            sys.exit(1)
    
    def generate_summary(self) -> Dict[str, Any]:
        """로그 요약 정보를 생성합니다."""
        summary = {
            'total_logs': len(self.logs),
            'requests': len(self.requests),
            'responses': len(self.responses),
            'errors': len(self.errors),
            'services': defaultdict(int),
            'tools': defaultdict(int),
            'event_types': defaultdict(int),
            'performance_stats': {
                'avg_execution_time_ms': 0,
                'total_execution_time_ms': 0,
                'success_count': 0,
                'error_count': 0
            }
        }
        
        # 서비스별, 도구별, 이벤트 타입별 통계
        for log in self.logs:
            event_type = log.get('event', '')
            service = log.get('service', 'unknown')
            tool = log.get('tool', 'unknown')
            
            summary['services'][service] += 1
            summary['tools'][tool] += 1
            summary['event_types'][event_type] += 1
            
            # 성능 통계
            if event_type == 'MCP_RESPONSE':
                exec_time = log.get('execution_time_ms', 0)
                summary['performance_stats']['total_execution_time_ms'] += exec_time
                summary['performance_stats']['success_count'] += 1
            elif event_type == 'MCP_ERROR':
                summary['performance_stats']['error_count'] += 1
        
        # 평균 실행 시간 계산
        if summary['performance_stats']['success_count'] > 0:
            summary['performance_stats']['avg_execution_time_ms'] = (
                summary['performance_stats']['total_execution_time_ms'] / 
                summary['performance_stats']['success_count']
            )
        
        return summary
    
    def get_request_response_pairs(self) -> List[Dict[str, Any]]:
        """요청-응답 쌍을 반환합니다."""
        pairs = []
        
        for request_id, request in self.requests.items():
            response = self.responses.get(request_id)
            pair = {
                'request_id': request_id,
                'request': request,
                'response': response,
                'has_response': response is not None
            }
            pairs.append(pair)
        
        return pairs
    
    def filter_by_service(self, service: str) -> List[Dict[str, Any]]:
        """특정 서비스의 로그만 필터링합니다."""
        return [log for log in self.logs if log.get('service') == service]
    
    def filter_by_tool(self, tool: str) -> List[Dict[str, Any]]:
        """특정 도구의 로그만 필터링합니다."""
        return [log for log in self.logs if log.get('tool') == tool]
    
    def export_to_json(self, filename: str, data: Any) -> None:
        """데이터를 JSON 파일로 내보냅니다."""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            print(f"데이터가 {filename}에 저장되었습니다.")
        except Exception as e:
            print(f"Error: 파일 저장 오류: {e}")
    
    def print_summary(self) -> None:
        """요약 정보를 콘솔에 출력합니다."""
        summary = self.generate_summary()
        
        print("\n" + "="*60)
        print("MCP Atlassian 로그 분석 요약")
        print("="*60)
        print(f"총 로그 수: {summary['total_logs']}")
        print(f"요청 수: {summary['requests']}")
        print(f"응답 수: {summary['responses']}")
        print(f"오류 수: {summary['errors']}")
        
        print(f"\n서비스별 통계:")
        for service, count in summary['services'].items():
            print(f"  {service}: {count}")
        
        print(f"\n도구별 통계:")
        for tool, count in summary['tools'].items():
            print(f"  {tool}: {count}")
        
        print(f"\n이벤트 타입별 통계:")
        for event_type, count in summary['event_types'].items():
            print(f"  {event_type}: {count}")
        
        perf = summary['performance_stats']
        print(f"\n성능 통계:")
        print(f"  평균 실행 시간: {perf['avg_execution_time_ms']:.2f}ms")
        print(f"  총 실행 시간: {perf['total_execution_time_ms']:.2f}ms")
        print(f"  성공: {perf['success_count']}")
        print(f"  오류: {perf['error_count']}")
        
        if self.errors:
            print(f"\n오류 목록:")
            for error in self.errors[:5]:  # 최대 5개만 표시
                print(f"  {error.get('tool', 'unknown')}: {error.get('error_message', 'unknown error')}")
            if len(self.errors) > 5:
                print(f"  ... 및 {len(self.errors) - 5}개 더")


def main():
    parser = argparse.ArgumentParser(description='MCP Atlassian 로그 분석기')
    parser.add_argument('--input', '-i', required=True, help='입력 로그 파일')
    parser.add_argument('--output', '-o', help='출력 파일 (JSON 형식)')
    parser.add_argument('--format', '-f', choices=['summary', 'pairs', 'raw'], 
                       default='summary', help='출력 형식')
    parser.add_argument('--filter', choices=['jira', 'confluence'], 
                       help='서비스별 필터링')
    parser.add_argument('--tool', help='특정 도구 필터링')
    
    args = parser.parse_args()
    
    analyzer = LogAnalyzer()
    analyzer.parse_log_file(args.input)
    
    if not analyzer.logs:
        print("분석할 로그가 없습니다.")
        return
    
    # 필터링 적용
    if args.filter:
        analyzer.logs = analyzer.filter_by_service(args.filter)
        print(f"{args.filter} 서비스 로그만 필터링되었습니다.")
    
    if args.tool:
        analyzer.logs = analyzer.filter_by_tool(args.tool)
        print(f"{args.tool} 도구 로그만 필터링되었습니다.")
    
    # 출력 형식에 따른 처리
    if args.format == 'summary':
        if args.output:
            analyzer.export_to_json(args.output, analyzer.generate_summary())
        else:
            analyzer.print_summary()
    
    elif args.format == 'pairs':
        pairs = analyzer.get_request_response_pairs()
        if args.output:
            analyzer.export_to_json(args.output, pairs)
        else:
            print(f"요청-응답 쌍: {len(pairs)}개")
            for pair in pairs[:3]:  # 처음 3개만 표시
                print(f"Request ID: {pair['request_id']}")
                print(f"Tool: {pair['request'].get('tool')}")
                print(f"Has Response: {pair['has_response']}")
                print()
    
    elif args.format == 'raw':
        if args.output:
            analyzer.export_to_json(args.output, analyzer.logs)
        else:
            print(f"총 {len(analyzer.logs)}개의 로그 엔트리")


if __name__ == '__main__':
    main() 