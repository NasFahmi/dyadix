import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflows.nodes.structure_mapper import structure_mapper_node

def make_state(direction, entry, bear_ob_top=None, bull_ob_bottom=None,
               high_pools=None, low_pools=None, pdh=None, pdl=None,
               recent_sweeps=None, atr=200.0):
    bias_map = {"bearish": "Strong Bearish", "bullish": "Strong Bullish", "neutral": "Neutral"}
    bear_ob = {"top": bear_ob_top, "bottom": bear_ob_top - 100} if bear_ob_top else None
    bull_ob = {"top": bull_ob_bottom + 100, "bottom": bull_ob_bottom} if bull_ob_bottom else None
    return {
        "symbol": "TEST", "realtime_price": entry,
        "aggregated_verdict": {"consensus_bias": bias_map.get(direction, "Neutral")},
        "market_data": {
            "order_block_1h": {
                "nearest_bearish_ob": bear_ob,
                "nearest_bullish_ob": bull_ob,
            },
            "volatility_5m": {"atr": atr},
        },
        "liquidity_data": {
            "liquidity_pools": {"highs": high_pools or [], "lows": low_pools or []},
            "key_levels": {"pdh": pdh, "pdl": pdl},
            "recent_sweeps": recent_sweeps or [],
        },
        "errors": [],
    }

tests = [
    ("T1 SELL cascade ke PDL",
     make_state("bearish", 61905, bear_ob_top=62117,
                low_pools=[{"price": 61500, "strength": "Strong", "touches": 4}],
                pdl=61000, atr=212.0),
     False),

    ("T2 SELL TP langsung level 1",
     make_state("bearish", 61905, bear_ob_top=62050,
                low_pools=[{"price": 61000, "strength": "Strong", "touches": 5}],
                atr=150.0),
     False),

    ("T3 SELL hanya PDL valid (pools Moderate)",
     make_state("bearish", 61905, bear_ob_top=62100,
                low_pools=[
                    {"price": 61600, "strength": "Moderate", "touches": 2},
                    {"price": 61400, "strength": "Moderate", "touches": 1},
                ],
                pdl=61000, atr=200.0),
     False),

    ("T4 SELL swept pool butuh RR >= 2.0",
     make_state("bearish", 61905, bear_ob_top=62100,
                low_pools=[{"price": 61500, "strength": "Strong", "touches": 4}],
                pdl=61000,
                recent_sweeps=[{"level": "Low Pool", "level_price": 61500, "type": "Bullish Sweep"}],
                atr=200.0),
     False),

    ("T5 SELL tidak ada TP valid -> WAIT",
     make_state("bearish", 61905, bear_ob_top=62500,
                low_pools=[{"price": 61800, "strength": "Moderate", "touches": 2}],
                pdl=None, atr=200.0),
     True),

    ("T6 Neutral bias -> WAIT",
     make_state("neutral", 61905, atr=200.0),
     True),

    ("T7 BUY structural setup",
     make_state("bullish", 61200, bull_ob_bottom=61000,
                high_pools=[{"price": 61600, "strength": "Strong", "touches": 4}],
                pdh=62000, atr=200.0),
     False),
]

passed = 0
failed = 0
for name, state, expect_wait in tests:
    try:
        res = structure_mapper_node(state)
        sm = res.get("structure_map", {})
        got_wait = sm.get("should_wait", True)
        if got_wait == expect_wait:
            if not expect_wait:
                print("PASS [" + name + "]")
                print("  SL=" + str(sm["recommended_sl"]) + " (" + sm["sl_type"] + ")")
                print("  TP=" + str(sm["recommended_tp"]) + " (" + sm["tp_type"] + ")")
                print("  RR=1:" + str(sm["natural_rr"]) + " | cascade_attempts=" + str(sm["cascade_attempts"]))
                for log in sm.get("cascade_log", []):
                    icon = "OK" if log["result"] == "ACCEPTED" else "--"
                    print("    [" + icon + "] " + log["type"] + " @" + str(log["level"]) + " RR=" + str(log["rr"]) + " -> " + log["result"])
            else:
                print("PASS [" + name + "] should_wait=True: " + sm.get("wait_reason", ""))
            passed += 1
        else:
            print("FAIL [" + name + "] expected should_wait=" + str(expect_wait) + " got " + str(got_wait))
            print("  map=" + str(sm))
            failed += 1
    except Exception as e:
        print("ERROR [" + name + "]: " + str(e))
        import traceback
        traceback.print_exc()
        failed += 1

print("")
print("Results: " + str(passed) + " passed, " + str(failed) + " failed out of " + str(len(tests)))
