"""
Phase 3.7 — Liquidity + CHoCH Confluence Engine.
Combines sweep, CHoCH, BOS into high-probability setups.
"""
from typing import Optional, Dict, List


def evaluate_confluence(sweep: Optional[Dict],
                        choch: Optional[Dict],
                        bos_event: Optional[Dict],
                        structure_shift: Dict) -> Optional[Dict]:
    """
    Phase 3.7: Produces a setup signal when multiple conditions align.

    Strongest setup: Sweep + CHoCH + BOS
    Returns signal dict or None.
    """
    if not sweep and not choch:
        return None

    score = 0
    reasons = []
    side = None

    # Determine direction from CHoCH
    if choch:
        if choch["type"] == "BULLISH_CHOCH":
            side = "LONG"
        else:
            side = "SHORT"
        score += 2
        reasons.append(f"{choch['type']} (conf={choch['confidence']:.2f})")

    # Sweep alignment
    if sweep:
        if side == "LONG" and sweep["type"] == "BUY_SIDE_SWEEP":
            score += 2
            reasons.append(f"BUY_SIDE_SWEEP ({sweep['strength']})")
        elif side == "SHORT" and sweep["type"] == "SELL_SIDE_SWEEP":
            score += 2
            reasons.append(f"SELL_SIDE_SWEEP ({sweep['strength']})")
        elif side is None:
            # Infer direction from sweep
            if sweep["type"] == "BUY_SIDE_SWEEP":
                side = "LONG"
            else:
                side = "SHORT"
            score += 1
            reasons.append(f"{sweep['type']} (no CHoCH yet)")

    # BOS confirmation
    if bos_event:
        if (side == "LONG" and bos_event["type"] == "BOS_UP") or \
           (side == "SHORT" and bos_event["type"] == "BOS_DOWN"):
            score += 2
            reasons.append(f"BOS confirmed {bos_event['type']}")

    # Structure shift
    if structure_shift.get("structure_shift") and structure_shift.get("direction"):
        expected = "UP" if side == "LONG" else "DOWN"
        if structure_shift["direction"] == expected:
            score += 1
            reasons.append("Structure shift confirmed")

    if side is None or score < 3:
        return None

    quality = "HIGH" if score >= 5 else ("MEDIUM" if score >= 3 else "LOW")

    return {
        "setup": f"{side}_REVERSAL",
        "side": side,
        "quality": quality,
        "score": score,
        "reasons": reasons,
        "sweep": sweep,
        "choch": choch,
    }
