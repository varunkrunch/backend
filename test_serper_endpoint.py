#!/usr/bin/env python3
"""
Test script for Serper.dev Google search endpoint
"""

import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_serper_endpoint():
    """Test the Serper endpoint with a simple search query."""
    
    # Configuration
    base_url = "http://localhost:8000"
    endpoint = f"{base_url}/api/v1/serper/search/simple"
    
    # Get API key from environment
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("❌ SERPER_API_KEY not found in environment variables")
        print("Please set your Serper API key:")
        print("export SERPER_API_KEY='your_api_key_here'")
        return False
    
    # Test parameters
    params = {
        "query": "FastAPI Python web framework",
        "num_results": 5,
        "country": "us",
        "language": "en"
    }
    
    headers = {
        "X-Serper-Api-Key": api_key,
        "Content-Type": "application/json"
    }
    
    print(f"🔍 Testing Serper endpoint: {endpoint}")
    print(f"📝 Query: {params['query']}")
    print(f"🔑 Using API key: {api_key[:10]}...")
    
    try:
        # Make the request
        response = requests.get(endpoint, params=params, headers=headers, timeout=30)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Success! Search results:")
            print(f"📈 Total results: {data.get('total_results', 'N/A')}")
            print(f"⏱️ Search time: {data.get('search_time', 'N/A')} seconds")
            print("\n🔗 Results:")
            
            for i, result in enumerate(data.get('results', []), 1):
                print(f"\n{i}. {result.get('title', 'No title')}")
                print(f"   🔗 {result.get('link', 'No link')}")
                print(f"   📄 {result.get('snippet', 'No snippet')[:100]}...")
            
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Could not connect to the FastAPI server")
        print("Make sure the server is running on http://localhost:8000")
        return False
    except requests.exceptions.Timeout:
        print("❌ Timeout Error: Request took too long")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def test_serper_post_endpoint():
    """Test the POST endpoint for Serper search."""
    
    base_url = "http://localhost:8000"
    endpoint = f"{base_url}/api/v1/serper/search"
    
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        print("❌ SERPER_API_KEY not found in environment variables")
        return False
    
    # Test payload
    payload = {
        "query": "Python FastAPI tutorial",
        "num_results": 3,
        "country": "us",
        "language": "en",
        "safe_search": True
    }
    
    headers = {
        "X-Serper-Api-Key": api_key,
        "Content-Type": "application/json"
    }
    
    print(f"\n🔍 Testing Serper POST endpoint: {endpoint}")
    print(f"📝 Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Success! Search results:")
            print(f"📈 Total results: {data.get('total_results', 'N/A')}")
            print(f"⏱️ Search time: {data.get('search_time', 'N/A')} seconds")
            print("\n🔗 Organic Results:")
            
            for i, result in enumerate(data.get('organic_results', []), 1):
                print(f"\n{i}. {result.get('title', 'No title')}")
                print(f"   🔗 {result.get('link', 'No link')}")
                print(f"   📄 {result.get('snippet', 'No snippet')[:100]}...")
            
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Testing Serper.dev Google Search Endpoint")
    print("=" * 50)
    
    # Test GET endpoint
    success1 = test_serper_endpoint()
    
    # Test POST endpoint
    success2 = test_serper_post_endpoint()
    
    print("\n" + "=" * 50)
    if success1 and success2:
        print("🎉 All tests passed! Serper endpoint is working correctly.")
    else:
        print("❌ Some tests failed. Check the output above for details.")
        print("\n💡 Troubleshooting tips:")
        print("1. Make sure your SERPER_API_KEY is set correctly")
        print("2. Ensure the FastAPI server is running on localhost:8000")
        print("3. Check that the serper router is properly integrated")
        print("4. Verify your Serper API key is valid and has credits")





