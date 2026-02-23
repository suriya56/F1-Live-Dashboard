#!/usr/bin/env python3
"""
Test script to verify f1-dash installation
"""

def test_imports():
    """Test that all modules can be imported"""
    try:
        import f1_dash
        print("✓ f1_dash module imported successfully")
        
        from f1_dash import F1Dashboard, main, AVAILABLE_SEASONS
        print("✓ Main components imported successfully")
        
        print(f"✓ Available seasons: {AVAILABLE_SEASONS}")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_dependencies():
    """Test that key dependencies are available"""
    deps = ['fastf1', 'textual', 'pandas', 'rich', 'matplotlib']
    
    for dep in deps:
        try:
            __import__(dep)
            print(f"✓ {dep} available")
        except ImportError as e:
            print(f"✗ {dep} not available: {e}")
            return False
    
    return True

def test_cache():
    """Test cache manager (optional)"""
    try:
        from f1_dash.cache_manager import CacheManager
        print("✓ Cache manager available")
        return True
    except Exception as e:
        print(f"⚠ Cache manager not available (optional): {e}")
        return True  # Cache is optional

def main():
    """Run all tests"""
    print("Testing f1-dash installation...")
    print("=" * 40)
    
    tests = [
        ("Dependencies", test_dependencies),
        ("Imports", test_imports),
        ("Cache", test_cache),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n{name}:")
        result = test_func()
        results.append(result)
    
    print("\n" + "=" * 40)
    if all(results):
        print("✓ All tests passed! f1-dash is ready to use.")
        print("\nRun 'f1-dash' to start the application.")
    else:
        print("✗ Some tests failed. Check the errors above.")
    
    return all(results)

if __name__ == "__main__":
    main()
