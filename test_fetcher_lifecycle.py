#!/usr/bin/env python
"""
Fetcher 인스턴스 생명주기 테스트
"""

import gc
import weakref
from mcp_atlassian.jira import JiraFetcher, JiraConfig

def test_fetcher_lifecycle():
    """Fetcher 인스턴스가 자동으로 삭제되는지 테스트"""
    
    # 1. Fetcher 인스턴스 생성
    config = JiraConfig(
        url="https://test.atlassian.net",
        auth_type="basic",
        username="test",
        api_token="test"
    )
    
    def create_and_use_fetcher():
        """함수 내에서 fetcher 생성 및 사용"""
        fetcher = JiraFetcher(config=config)
        
        # Weak reference로 추적
        weak_ref = weakref.ref(fetcher)
        print(f"Fetcher 생성됨: {id(fetcher)}")
        print(f"Weak reference 생성됨: {weak_ref}")
        
        # 함수 종료 시 fetcher 참조가 사라짐
        return weak_ref
    
    # 2. 함수 실행
    weak_ref = create_and_use_fetcher()
    
    # 3. 강제 가비지 컬렉션
    gc.collect()
    
    # 4. 객체가 삭제되었는지 확인
    if weak_ref() is None:
        print("✅ Fetcher 인스턴스가 자동으로 삭제되었습니다!")
    else:
        print("❌ Fetcher 인스턴스가 아직 메모리에 있습니다.")
        print(f"   객체 ID: {id(weak_ref())}")

if __name__ == "__main__":
    test_fetcher_lifecycle() 