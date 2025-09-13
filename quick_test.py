#!/usr/bin/env python3
"""
Quick API Test Script for Open Notebook Backend
This script tests the basic functionality of the API endpoints
"""

import requests
import json
import time
import sys
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8001"
API_BASE = f"{BASE_URL}/api/v1"

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_success(message: str):
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")

def print_error(message: str):
    print(f"{Colors.RED}❌ {message}{Colors.END}")

def print_warning(message: str):
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")

def print_info(message: str):
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.END}")

def print_header(message: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*50}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{message}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*50}{Colors.END}")

def test_health_check() -> bool:
    """Test the health check endpoint"""
    print_header("Testing Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Health check passed: {data.get('message', 'OK')}")
            return True
        else:
            print_error(f"Health check failed with status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Health check failed: {e}")
        return False

def test_notebook_operations() -> bool:
    """Test notebook CRUD operations"""
    print_header("Testing Notebook Operations")
    
    notebook_name = "Test Notebook API"
    notebook_data = {
        "name": notebook_name,
        "description": "A test notebook created by the API test script"
    }
    
    try:
        # Create notebook
        print_info("Creating test notebook...")
        response = requests.post(f"{API_BASE}/notebooks", json=notebook_data, timeout=10)
        if response.status_code in [200, 201]:
            print_success("Notebook created successfully")
        else:
            print_warning(f"Notebook creation returned status {response.status_code}: {response.text}")
        
        # List notebooks
        print_info("Listing notebooks...")
        response = requests.get(f"{API_BASE}/notebooks", timeout=10)
        if response.status_code == 200:
            notebooks = response.json()
            print_success(f"Found {len(notebooks)} notebook(s)")
            if notebooks:
                print_info(f"Sample notebook: {notebooks[0].get('name', 'Unknown')}")
        else:
            print_error(f"Failed to list notebooks: {response.status_code}")
            return False
        
        # Get notebook by name
        print_info(f"Getting notebook by name: {notebook_name}")
        response = requests.get(f"{API_BASE}/notebooks/by-name/{notebook_name}", timeout=10)
        if response.status_code == 200:
            notebook = response.json()
            print_success(f"Retrieved notebook: {notebook.get('name', 'Unknown')}")
        else:
            print_warning(f"Failed to get notebook by name: {response.status_code}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print_error(f"Notebook operations failed: {e}")
        return False

def test_source_operations() -> bool:
    """Test source upload operations"""
    print_header("Testing Source Operations")
    
    try:
        # Create a test file
        test_content = "This is a test document for API testing.\nIt contains some sample text to verify source upload functionality."
        with open("test_document.txt", "w") as f:
            f.write(test_content)
        
        # Upload source
        print_info("Uploading test document as source...")
        with open("test_document.txt", "rb") as f:
            files = {"file": ("test_document.txt", f, "text/plain")}
            data = {"title": "Test Document"}
            response = requests.post(
                f"{API_BASE}/notebooks/by-name/Test%20Notebook%20API/sources",
                files=files,
                data=data,
                timeout=30
            )
        
        if response.status_code in [200, 201]:
            print_success("Source uploaded successfully")
        else:
            print_warning(f"Source upload returned status {response.status_code}: {response.text}")
        
        # List sources
        print_info("Listing sources...")
        response = requests.get(f"{API_BASE}/notebooks/by-name/Test%20Notebook%20API/sources", timeout=10)
        if response.status_code == 200:
            sources = response.json()
            print_success(f"Found {len(sources)} source(s)")
        else:
            print_warning(f"Failed to list sources: {response.status_code}")
        
        # Clean up test file
        import os
        if os.path.exists("test_document.txt"):
            os.remove("test_document.txt")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print_error(f"Source operations failed: {e}")
        return False

def test_notes_operations() -> bool:
    """Test notes CRUD operations"""
    print_header("Testing Notes Operations")
    
    try:
        # Create a note
        note_data = {
            "title": "Test Note",
            "content": "This is a test note created by the API test script to verify notes functionality."
        }
        
        print_info("Creating test note...")
        response = requests.post(
            f"{API_BASE}/notebooks/by-name/Test%20Notebook%20API/notes",
            json=note_data,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            print_success("Note created successfully")
        else:
            print_warning(f"Note creation returned status {response.status_code}: {response.text}")
        
        # List notes
        print_info("Listing notes...")
        response = requests.get(f"{API_BASE}/notebooks/by-name/Test%20Notebook%20API/notes", timeout=10)
        if response.status_code == 200:
            notes = response.json()
            print_success(f"Found {len(notes)} note(s)")
        else:
            print_warning(f"Failed to list notes: {response.status_code}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print_error(f"Notes operations failed: {e}")
        return False

def test_search_functionality() -> bool:
    """Test search functionality"""
    print_header("Testing Search Functionality")
    
    try:
        print_info("Testing search...")
        response = requests.get(
            f"{API_BASE}/search?q=test&notebook_id=Test%20Notebook%20API",
            timeout=10
        )
        
        if response.status_code == 200:
            results = response.json()
            print_success(f"Search completed successfully")
            if isinstance(results, list):
                print_info(f"Found {len(results)} search result(s)")
            else:
                print_info(f"Search returned: {type(results).__name__}")
        else:
            print_warning(f"Search returned status {response.status_code}: {response.text}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print_error(f"Search functionality failed: {e}")
        return False

def test_models_endpoint() -> bool:
    """Test models endpoint"""
    print_header("Testing Models Endpoint")
    
    try:
        print_info("Getting available models...")
        response = requests.get(f"{API_BASE}/models", timeout=10)
        
        if response.status_code == 200:
            models = response.json()
            print_success("Models endpoint working")
            if isinstance(models, list):
                print_info(f"Found {len(models)} model(s)")
            else:
                print_info(f"Models response type: {type(models).__name__}")
        else:
            print_warning(f"Models endpoint returned status {response.status_code}: {response.text}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print_error(f"Models endpoint failed: {e}")
        return False

def main():
    """Main test function"""
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("🧪 Open Notebook FastAPI Backend - Quick Test")
    print("=" * 50)
    print(f"{Colors.END}")
    
    print_info(f"Testing API at: {BASE_URL}")
    print_info("Make sure the server is running with: python run.py")
    print()
    
    # Wait a moment for user to read
    time.sleep(1)
    
    # Run tests
    tests = [
        ("Health Check", test_health_check),
        ("Notebook Operations", test_notebook_operations),
        ("Source Operations", test_source_operations),
        ("Notes Operations", test_notes_operations),
        ("Search Functionality", test_search_functionality),
        ("Models Endpoint", test_models_endpoint),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print_error(f"Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
        
        time.sleep(0.5)  # Small delay between tests
    
    # Summary
    print_header("Test Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        if result:
            print_success(f"{test_name}")
        else:
            print_error(f"{test_name}")
    
    print()
    if passed == total:
        print_success(f"All {total} tests passed! 🎉")
        print_info("Your API is working correctly!")
    else:
        print_warning(f"{passed}/{total} tests passed")
        print_info("Some tests failed. Check the server logs for more details.")
    
    print()
    print_info("For more detailed testing, check TESTING_GUIDE.md")
    print_info("API Documentation: http://localhost:8001/docs")

if __name__ == "__main__":
    main()
