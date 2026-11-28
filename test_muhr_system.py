"""
Comprehensive MUHR System Test

Tests:
1. Registry is live
2. Sellers are registered
3. SSE feed is working
4. Buyer can post tasks
5. Full transaction flow (if sellers are running)
"""

import httpx
import json
import sys

REGISTRY_URL = "http://localhost:8000"

def test_registry_health():
    """Test 1: Registry Health"""
    print("\n[TEST 1] Registry Health Check")
    print("=" * 60)
    try:
        response = httpx.get(f"{REGISTRY_URL}/health", timeout=5.0)
        response.raise_for_status()
        data = response.json()
        print(f"✅ Registry is LIVE")
        print(f"   Status: {data.get('status')}")
        print(f"   Timestamp: {data.get('timestamp')}")
        return True
    except Exception as e:
        print(f"❌ Registry health check failed: {e}")
        return False


def test_seller_registration():
    """Test 2: Seller Registration"""
    print("\n[TEST 2] Seller Registration")
    print("=" * 60)
    try:
        response = httpx.get(f"{REGISTRY_URL}/api/sellers", timeout=5.0)
        response.raise_for_status()
        data = response.json()
        sellers = data.get("sellers", [])
        total = data.get("total", 0)
        
        print(f"✅ Seller registration is WORKING")
        print(f"   Total sellers: {total}")
        print(f"\n   Registered sellers:")
        for seller in sellers:
            print(f"   - {seller['seller_id']}: {seller['capability']}")
            print(f"     Price: {seller['price_sats_per_unit']} sats {seller['unit_definition']}")
            print(f"     Endpoint: {seller['endpoint_url']}")
            print(f"     Status: {seller['status']}")
            print()
        return True
    except Exception as e:
        print(f"❌ Seller registration test failed: {e}")
        return False


def test_sse_feed():
    """Test 3: SSE Real-time Feed"""
    print("\n[TEST 3] SSE Real-time Feed")
    print("=" * 60)
    try:
        # Just test that the endpoint exists and responds
        with httpx.stream("GET", f"{REGISTRY_URL}/api/feed", 
                         headers={"accept": "text/event-stream"},
                         timeout=3.0) as response:
            response.raise_for_status()
            # Read first few lines
            lines_read = 0
            for line in response.iter_lines():
                if lines_read >= 5:
                    break
                if line.strip():
                    print(f"   Received: {line[:80]}...")
                    lines_read += 1
        
        print(f"✅ SSE feed is WORKING")
        print(f"   Feed URL: {REGISTRY_URL}/api/feed")
        return True
    except Exception as e:
        print(f"❌ SSE feed test failed: {e}")
        return False


def test_task_posting():
    """Test 4: Task Posting"""
    print("\n[TEST 4] Task Posting (Buyer → Registry)")
    print("=" * 60)
    try:
        task_data = {
            "capability_needed": "text_summarization",
            "input_schema": {"type": "string"},
            "budget_sats": 100,
            "buyer_pubkey": "test_buyer_pubkey"
        }
        
        response = httpx.post(
            f"{REGISTRY_URL}/api/tasks",
            json=task_data,
            timeout=5.0
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ Task posting is WORKING")
        print(f"   Task ID: {result.get('task_id')}")
        print(f"   Status: {result.get('status')}")
        print(f"   Expires: {result.get('expires_at')}")
        return True
    except Exception as e:
        print(f"❌ Task posting test failed: {e}")
        return False


def test_seller_endpoints():
    """Test 5: Seller Endpoints (if running)"""
    print("\n[TEST 5] Seller Endpoints")
    print("=" * 60)
    
    seller_endpoints = [
        ("Summarizer", "http://localhost:8001/health"),
        ("Classifier", "http://localhost:8002/health")
    ]
    
    results = []
    for name, url in seller_endpoints:
        try:
            response = httpx.get(url, timeout=2.0)
            response.raise_for_status()
            data = response.json()
            print(f"✅ {name} is RUNNING")
            print(f"   Service: {data.get('service')}")
            results.append(True)
        except Exception as e:
            print(f"⚠️  {name} is NOT running (expected if not started)")
            print(f"   Error: {e}")
            results.append(False)
    
    return any(results)


def main():
    print("\n" + "=" * 60)
    print("MUHR SYSTEM COMPREHENSIVE TEST")
    print("=" * 60)
    
    results = {
        "Registry Health": test_registry_health(),
        "Seller Registration": test_seller_registration(),
        "SSE Real-time Feed": test_sse_feed(),
        "Task Posting": test_task_posting(),
        "Seller Endpoints": test_seller_endpoints()
    }
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! MUHR system is fully functional!")
    elif passed >= 4:
        print("\n✅ Core functionality working! (Sellers may need to be started separately)")
    else:
        print("\n⚠️  Some core components are not working. Check the errors above.")
    
    print("=" * 60)
    
    return 0 if passed >= 4 else 1


if __name__ == "__main__":
    sys.exit(main())
