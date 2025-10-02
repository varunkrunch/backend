#!/usr/bin/env python3
"""
Test script for GPTR.dev researcher AI endpoint
"""

import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_gptr_health():
    """Test the health check endpoint."""
    
    base_url = "http://localhost:8000"
    endpoint = f"{base_url}/api/v1/gptr/health"
    
    print(f"🔍 Testing GPTR health endpoint: {endpoint}")
    
    try:
        response = requests.get(endpoint, timeout=10)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Health check successful!")
            print(f"📈 Status: {data.get('status', 'N/A')}")
            print(f"🔑 Tavily configured: {data.get('tavily_configured', 'N/A')}")
            print(f"🤖 OpenAI configured: {data.get('openai_configured', 'N/A')}")
            print(f"💬 Message: {data.get('message', 'N/A')}")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Could not connect to the FastAPI server")
        print("Make sure the server is running on http://localhost:8000")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def test_gptr_simple_research():
    """Test the simple research endpoint."""
    
    base_url = "http://localhost:8000"
    endpoint = f"{base_url}/api/v1/gptr/research/simple"
    
    # Test parameters
    params = {
        "query": "What is artificial intelligence?",
        "max_results": 3,
        "include_answer": True
    }
    
    print(f"\n🔍 Testing GPTR simple research endpoint: {endpoint}")
    print(f"📝 Query: {params['query']}")
    
    try:
        response = requests.get(endpoint, params=params, timeout=60)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Research successful!")
            print(f"📈 Query: {data.get('query', 'N/A')}")
            print(f"📊 Total results: {data.get('total_results', 'N/A')}")
            print(f"⏱️ Search time: {data.get('search_time', 'N/A')} seconds")
            
            if data.get('answer'):
                print(f"\n🤖 AI Answer:")
                print(f"{data.get('answer', '')[:300]}...")
            
            print(f"\n🔗 Results:")
            for i, result in enumerate(data.get('results', [])[:2], 1):
                print(f"\n{i}. {result.get('title', 'No title')}")
                print(f"   🔗 {result.get('url', 'No URL')}")
                print(f"   📄 {result.get('content', 'No content')[:100]}...")
                if result.get('score'):
                    print(f"   📊 Score: {result.get('score')}")
            
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Timeout Error: Research took too long")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def test_gptr_advanced_research():
    """Test the advanced research endpoint with POST."""
    
    base_url = "http://localhost:8000"
    endpoint = f"{base_url}/api/v1/gptr/research"
    
    # Test payload
    payload = {
        "query": "Latest developments in quantum computing 2024",
        "max_results": 5,
        "search_depth": "advanced",
        "include_answer": True,
        "include_raw_content": False,
        "include_domains": ["arxiv.org", "nature.com", "ieee.org"]
    }
    
    print(f"\n🔍 Testing GPTR advanced research endpoint: {endpoint}")
    print(f"📝 Query: {payload['query']}")
    print(f"🎯 Domains: {payload['include_domains']}")
    
    try:
        response = requests.post(endpoint, json=payload, timeout=90)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Advanced research successful!")
            print(f"📈 Query: {data.get('query', 'N/A')}")
            print(f"📊 Total results: {data.get('total_results', 'N/A')}")
            print(f"⏱️ Search time: {data.get('search_time', 'N/A')} seconds")
            
            if data.get('answer'):
                print(f"\n🤖 AI Answer:")
                print(f"{data.get('answer', '')[:400]}...")
            
            print(f"\n🔗 Sources used:")
            for i, source in enumerate(data.get('sources_used', [])[:3], 1):
                print(f"{i}. {source}")
            
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Timeout Error: Advanced research took too long")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Testing GPTR.dev Researcher AI Endpoint")
    print("=" * 60)
    
    # Test health check
    health_ok = test_gptr_health()
    
    if health_ok:
        # Test simple research
        simple_ok = test_gptr_simple_research()
        
        # Test advanced research
        advanced_ok = test_gptr_advanced_research()
        
        print("\n" + "=" * 60)
        if simple_ok and advanced_ok:
            print("🎉 All tests passed! GPTR researcher endpoint is working correctly.")
        else:
            print("❌ Some tests failed. Check the output above for details.")
    else:
        print("\n" + "=" * 60)
        print("❌ Health check failed. Please check your API keys and server status.")
        print("\n💡 Troubleshooting tips:")
        print("1. Make sure TAVILY_API_KEY is set in your .env file")
        print("2. Make sure OPENAI_API_KEY is set in your .env file")
        print("3. Ensure the FastAPI server is running on localhost:8000")
        print("4. Check that the gptr_researcher router is properly integrated")





