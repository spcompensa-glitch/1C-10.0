#!/usr/bin/env python3
"""
Test script to verify the three critical fixes:
1. CaptainAgent consensus threshold reduced from 50% to 40%
2. Bankroll ROI guarantee reduced from 80% to 60%
3. Moonbags UI shows "MOONBAG ACTIVE" instead of "ETERNAL SURF"
"""

import re
import sys

def test_captain_threshold():
    """Test that CaptainAgent consensus threshold is now 40% (or 35% with free slots)"""
    print("🔍 Testing CaptainAgent consensus threshold...")
    
    try:
        with open('services/agents/captain.py', 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # Fallback to different encoding
        with open('services/agents/captain.py', 'r', encoding='latin-1') as f:
            content = f.read()
    
    # Check if the threshold is now 40.0 instead of 50.0, and includes dynamic logic
    if 'required_confidence = 35.0 if free_slots >= 2 else 40.0' in content and 'if unified_score < required_confidence:' in content:
        print("✅ CaptainAgent consensus threshold correctly set to 40% (35% with 2+ free slots)")
        return True
    else:
        print("❌ CaptainAgent consensus threshold not found or not set correctly")
        return False

def test_bankroll_roi():
    """Test that Bankroll ROI guarantee is now 60%"""
    print("🔍 Testing Bankroll ROI guarantee...")
    
    try:
        with open('services/bankroll.py', 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        with open('services/bankroll.py', 'r', encoding='latin-1') as f:
            content = f.read()
    
    # Check if the ROI guarantee is now 60.0 instead of 80.0
    if 'is_profit_guaranteed = roi_at_sl >= 60.0' in content:
        print("✅ Bankroll ROI guarantee correctly set to 60%")
        return True
    else:
        print("❌ Bankroll ROI guarantee not found or not set to 60%")
        return False

def test_moonbags_ui():
    """Test that Moonbags UI shows 'MOONBAG ACTIVE' instead of 'ETERNAL SURF'"""
    print("🔍 Testing Moonbags UI...")
    
    try:
        with open('../frontend/cockpit.html', 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        with open('frontend/cockpit.html', 'r', encoding='latin-1') as f:
            content = f.read()
    
    # Check if "ETERNAL SURF" is removed and "MOONBAG ACTIVE" is added
    has_old_label = 'ETERNAL SURF' in content
    has_new_label = 'MOONBAG ACTIVE' in content
    
    if not has_old_label and has_new_label:
        print("✅ Moonbags UI correctly shows 'MOONBAG ACTIVE'")
        return True
    else:
        if has_old_label:
            print("❌ Moonbags UI still contains 'ETERNAL SURF'")
        if not has_new_label:
            print("❌ Moonbags UI does not contain 'MOONBAG ACTIVE'")
        return False

def test_roi_calculation_consistency():
    """Test that ROI calculation is consistent across components"""
    print("🔍 Testing ROI calculation consistency...")
    
    # Check execution_protocol.py
    try:
        with open('services/execution_protocol.py', 'r', encoding='utf-8') as f:
            exec_content = f.read()
    except UnicodeDecodeError:
        with open('services/execution_protocol.py', 'r', encoding='latin-1') as f:
            exec_content = f.read()
    
    # Check flash_agent.py
    try:
        with open('services/agents/flash_agent.py', 'r', encoding='utf-8') as f:
            flash_content = f.read()
    except UnicodeDecodeError:
        with open('services/agents/flash_agent.py', 'r', encoding='latin-1') as f:
            flash_content = f.read()
    
    # Both should use the same ROI formula: price_diff * leverage * 100
    exec_has_formula = 'roi = price_diff * leverage * 100' in exec_content
    flash_has_formula = 'return price_diff * leverage * 100' in flash_content
    
    if exec_has_formula and flash_has_formula:
        print("✅ ROI calculation is consistent across components")
        return True
    else:
        print("❌ ROI calculation inconsistency found")
        if not exec_has_formula:
            print("   - execution_protocol.py missing correct ROI formula")
        if not flash_has_formula:
            print("   - flash_agent.py missing correct ROI formula")
        return False

def test_ranging_ladder():
    """Test dynamic ranging ladder stop levels"""
    print("🔍 Testing Ranging Ladder stop levels...")
    from services.order_projection_service import order_projection_service
    
    # Test level at 12% ROI (should trigger BE stop at 0%)
    active_12 = order_projection_service.get_active_level(12.0, is_ranging=True)
    assert active_12 is not None
    assert active_12.stop_roi == 0.0
    
    # Test level at 25% ROI (should trigger trailing stop at 20.0%)
    active_25 = order_projection_service.get_active_level(25.0, is_ranging=True)
    assert active_25 is not None
    assert active_25.stop_roi == 20.0
    
    # Test level at 52.5% ROI (should trigger trailing stop at 47.5%)
    active_52 = order_projection_service.get_active_level(52.5, is_ranging=True)
    assert active_52 is not None
    assert active_52.stop_roi == 47.5
    
    print("✅ Ranging Ladder stop levels successfully verified!")
    return True

def main():
    """Run all tests"""
    print("🧪 Testing all critical fixes...\n")
    
    tests = [
        test_captain_threshold,
        test_bankroll_roi,
        test_moonbags_ui,
        test_roi_calculation_consistency,
        test_ranging_ladder
    ]
    
    results = []
    for test in tests:
        results.append(test())
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All fixes verified successfully!")
        return 0
    else:
        print("❌ Some fixes failed verification")
        return 1

if __name__ == "__main__":
    sys.exit(main())