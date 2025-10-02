#!/usr/bin/env python3
"""
Test script for note creation endpoints
Run this script to test the note creation functionality
"""

import asyncio
import aiohttp
import json
from datetime import datetime

# Configuration
API_BASE = "http://localhost:8000/api/v1"
NOTEBOOK_NAME = "Big Data Analytics"  # Use the notebook from the screenshot

async def test_note_creation():
    """Test the note creation endpoints"""
    
    # Test data
    test_note = {
        "title": "Test Note",
        "content": "This is a test note content",
        "note_type": "human"
    }
    
    print("🧪 Testing Note Creation Endpoints")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        
        # Test 1: Test the comprehensive endpoint
        print("\n1. Testing comprehensive test endpoint...")
        try:
            url = f"{API_BASE}/notes/test-create?notebook_name={NOTEBOOK_NAME}"
            async with session.post(url, json=test_note) as response:
                print(f"Status: {response.status}")
                if response.status == 201:
                    result = await response.json()
                    print("✅ Test endpoint successful!")
                    print(f"Success: {result.get('success')}")
                    print(f"Note ID: {result.get('note_id')}")
                    print(f"Notebook ID: {result.get('notebook_id')}")
                    print(f"Steps: {len(result.get('steps', []))}")
                    if result.get('errors'):
                        print(f"Errors: {result['errors']}")
                    if result.get('warnings'):
                        print(f"Warnings: {result['warnings']}")
                else:
                    error_text = await response.text()
                    print(f"❌ Test endpoint failed: {error_text}")
        except Exception as e:
            print(f"❌ Test endpoint error: {e}")
        
        # Test 2: Test the robust endpoint
        print("\n2. Testing robust endpoint...")
        try:
            url = f"{API_BASE}/notes/create?notebook_name={NOTEBOOK_NAME}"
            async with session.post(url, json=test_note) as response:
                print(f"Status: {response.status}")
                if response.status == 201:
                    result = await response.json()
                    print("✅ Robust endpoint successful!")
                    print(f"Note ID: {result.get('id')}")
                    print(f"Title: {result.get('title')}")
                    print(f"Content: {result.get('content')[:50]}...")
                    print(f"Note Type: {result.get('note_type')}")
                else:
                    error_text = await response.text()
                    print(f"❌ Robust endpoint failed: {error_text}")
        except Exception as e:
            print(f"❌ Robust endpoint error: {e}")
        
        # Test 3: Test listing notes
        print("\n3. Testing note listing...")
        try:
            url = f"{API_BASE}/notebooks/by-name/{NOTEBOOK_NAME}/notes"
            async with session.get(url) as response:
                print(f"Status: {response.status}")
                if response.status == 200:
                    notes = await response.json()
                    print(f"✅ Found {len(notes)} notes in notebook")
                    for note in notes[:3]:  # Show first 3 notes
                        print(f"  - {note.get('title')} ({note.get('id')})")
                else:
                    error_text = await response.text()
                    print(f"❌ Note listing failed: {error_text}")
        except Exception as e:
            print(f"❌ Note listing error: {e}")
        
        # Test 4: Test database query endpoint
        print("\n4. Testing database query endpoint...")
        try:
            url = f"{API_BASE}/test-db-query"
            async with session.get(url) as response:
                print(f"Status: {response.status}")
                if response.status == 200:
                    result = await response.json()
                    print("✅ Database query successful!")
                    print(f"Notes count: {result.get('notes_count')}")
                    print(f"Notebooks count: {result.get('notebooks_count')}")
                    print(f"Artifacts count: {result.get('artifacts_count')}")
                else:
                    error_text = await response.text()
                    print(f"❌ Database query failed: {error_text}")
        except Exception as e:
            print(f"❌ Database query error: {e}")

async def test_error_cases():
    """Test error cases"""
    
    print("\n🧪 Testing Error Cases")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        
        # Test 1: Empty content
        print("\n1. Testing empty content...")
        try:
            url = f"{API_BASE}/notes/create?notebook_name={NOTEBOOK_NAME}"
            test_note_empty = {
                "title": "Empty Note",
                "content": "",
                "note_type": "human"
            }
            async with session.post(url, json=test_note_empty) as response:
                print(f"Status: {response.status}")
                if response.status == 400:
                    result = await response.json()
                    print("✅ Correctly rejected empty content")
                    print(f"Error: {result.get('detail')}")
                else:
                    print(f"❌ Should have rejected empty content, got {response.status}")
        except Exception as e:
            print(f"❌ Error testing empty content: {e}")
        
        # Test 2: Invalid notebook
        print("\n2. Testing invalid notebook...")
        try:
            url = f"{API_BASE}/notes/create?notebook_name=InvalidNotebook"
            test_note = {
                "title": "Test Note",
                "content": "This is a test note",
                "note_type": "human"
            }
            async with session.post(url, json=test_note) as response:
                print(f"Status: {response.status}")
                if response.status == 404:
                    result = await response.json()
                    print("✅ Correctly rejected invalid notebook")
                    print(f"Error: {result.get('detail')}")
                else:
                    print(f"❌ Should have rejected invalid notebook, got {response.status}")
        except Exception as e:
            print(f"❌ Error testing invalid notebook: {e}")

async def main():
    """Main test function"""
    print("🚀 Starting Note Endpoint Tests")
    print(f"API Base: {API_BASE}")
    print(f"Notebook: {NOTEBOOK_NAME}")
    print(f"Time: {datetime.now()}")
    
    await test_note_creation()
    await test_error_cases()
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(main())

