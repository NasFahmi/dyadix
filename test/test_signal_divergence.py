"""
test/test_signal_divergence.py

Script untuk mengetes fitur Divergence Threshold pada SignalDetector.
Memastikan signal dengan bullish/bearish score yang terlalu dekat (sideways) di-filter.
"""

import sys
import os
import logging
from unittest.mock import MagicMock

# Setup path agar bisa import dari project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock dependencies sebelum import SignalDetector
mock_yaml = MagicMock()
sys.modules['yaml'] = mock_yaml

mock_config = MagicMock()
mock_config.get_config.return_value = {"trading": {"active_session": "all"}}
sys.modules['config.settings'] = mock_config

mock_session = MagicMock()
mock_session.is_active_session.return_value = True
sys.modules['utils.session_checker'] = mock_session

from pipelines.signal_detector import SignalDetector

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def run_test():
    print("\n" + "=" * 60)
    print(" SIGNAL DETECTOR - DIVERGENCE THRESHOLD TEST")
    print("=" * 60)

    # 1. Inisialisasi Detector dengan threshold 0.15
    min_conf = 0.40
    div_threshold = 0.15
    detector = SignalDetector(min_confidence=min_conf, divergence_threshold=div_threshold)

    # 2. Mock internal methods agar kita bisa kontrol output score
    detector._score_technical = MagicMock()
    detector._score_liquidity = MagicMock(return_value=(0.0, 0.0, [], []))
    detector._score_sentiment = MagicMock(return_value=(0.0, 0.0, [], []))
    detector._score_derivatives = MagicMock(return_value=(0.0, 0.0, [], []))
    detector._score_momentum_divergence = MagicMock(return_value=(0.0, 0.0, [], []))
    detector._score_order_block = MagicMock(return_value=(0.0, 0.0, [], []))

    test_cases = [
        {
            "name": "HIGH DIVERGENCE (Valid Signal)",
            "bull": 0.60, "bear": 0.10,
            "expected_has_signal": True,
            "description": "Bullish jauh lebih kuat (diff 0.50 > 0.15)"
        },
        {
            "name": "LOW DIVERGENCE (Sideways/Conflicting)",
            "bull": 0.45, "bear": 0.40,
            "expected_has_signal": False,
            "description": "Bullish & Bearish hampir sama kuat (diff 0.05 <= 0.15)"
        },
        {
            "name": "WEAK SIGNAL (Below Confidence)",
            "bull": 0.30, "bear": 0.05,
            "expected_has_signal": False,
            "description": "Meskipun diff 0.25 > 0.15, tapi bull 0.30 < min_conf 0.40"
        },
        {
            "name": "EXTREME SIDEWAYS (High Scores but Close)",
            "bull": 0.80, "bear": 0.75,
            "expected_has_signal": False,
            "description": "Keduanya sangat kuat tapi diff cuma 0.05 (Conflict)"
        }
    ]

    total_passed = 0
    for case in test_cases:
        print(f"\n--- Scenario: {case['name']} ---")
        print(f"    {case['description']}")
        
        # Atur return value mock technical
        detector._score_technical.return_value = (case['bull'], case['bear'], ["Reason"], ["Reason"])
        
        # Jalankan deteksi
        result = detector.detect({"pair": "BTCUSDT"})
        
        has_signal = result["has_potential_signal"]
        conf = result["confidence"]
        bull = result["scores"]["bullish"]
        bear = result["scores"]["bearish"]
        diff = abs(bull - bear)
        
        print(f"    Bull: {bull:.2f}, Bear: {bear:.2f}, Diff: {diff:.2f}")
        print(f"    Result: {'[SIGNAL]' if has_signal else '[NO SIGNAL]'} (Confidence: {conf})")
        
        if has_signal == case['expected_has_signal']:
            print("    STATUS: PASSED")
            total_passed += 1
        else:
            print(f"    STATUS: FAILED (Expected {case['expected_has_signal']})")

    print("\n" + "=" * 60)
    print(f" TEST COMPLETED: {total_passed}/{len(test_cases)} Passed")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_test()
