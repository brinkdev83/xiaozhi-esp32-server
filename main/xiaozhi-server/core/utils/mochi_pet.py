"""Mochi's pet state: needs that drift over time and change with care.

All needs run 0..100 where higher is better (full, rested, happy, clean).
The state lives in data/mochi_pet.json so it survives restarts, and time spent
offline is caught up (capped) on the next read.
"""

import json
import os
import threading
import time

from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

STATE_PATH = os.path.join("data", "mochi_pet.json")
MAX_CATCH_UP_HOURS = 48

# Change per hour.
AWAKE_DRIFT = {"verzadigd": -6, "energie": -4, "plezier": -5, "schoon": -3}
ASLEEP_DRIFT = {"verzadigd": -3, "energie": 15, "plezier": 0, "schoon": -1}
NEEDS = ("verzadigd", "energie", "plezier", "schoon")
LOW = 25

_lock = threading.Lock()


def _new_state(now):
    return {
        "verzadigd": 80, "energie": 80, "plezier": 80, "schoon": 90,
        "band": 10, "slaapt": False, "geboren": now, "bijgewerkt": now,
    }


def _clamp(value):
    return max(0, min(100, round(value, 1)))


def _load(now):
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = _new_state(now)
    hours = min(max(0.0, (now - state["bijgewerkt"]) / 3600), MAX_CATCH_UP_HOURS)
    drift = ASLEEP_DRIFT if state["slaapt"] else AWAKE_DRIFT
    for need in NEEDS:
        state[need] = _clamp(state[need] + drift[need] * hours)
    if state["slaapt"] and state["energie"] >= 100:
        state["slaapt"] = False  # uitgeslapen
    # Neglect wears the bond down a little.
    if any(state[n] < LOW for n in NEEDS):
        state["band"] = _clamp(state["band"] - hours)
    state["bijgewerkt"] = now
    return state


def _save(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def _word(need, value):
    if need == "energie":
        scale = ["uitgeput", "moe", "wat moe", "fit", "vol energie"]
    elif need == "verzadigd":
        scale = ["uitgehongerd", "flinke honger", "trek", "tevreden", "propvol"]
    elif need == "plezier":
        scale = ["verdrietig", "verveeld", "gewoon", "blij", "dolgelukkig"]
    else:
        scale = ["vies", "smoezelig", "redelijk schoon", "schoon", "glanzend schoon"]
    return scale[min(4, int(value // 20))]


def _describe(state):
    age_days = int((state["bijgewerkt"] - state["geboren"]) // 86400)
    parts = [f"{n}: {state[n]:.0f}/100 ({_word(n, state[n])})" for n in NEEDS]
    lines = [
        "Mochi slaapt nu." if state["slaapt"] else "Mochi is wakker.",
        "; ".join(parts) + ".",
        f"Band met de gebruiker: {state['band']:.0f}/100. Leeftijd: {age_days} dagen.",
    ]
    low = [n for n in NEEDS if state[n] < LOW]
    if low:
        lines.append("Dringend: " + ", ".join(low) + " is laag; laat dat merken.")
    return "\n".join(lines)


def status_text():
    """Current state as Dutch text for the system prompt."""
    with _lock:
        state = _load(time.time())
        _save(state)
        return _describe(state)


def apply(action, **kwargs):
    """Apply a care action; returns a Dutch result for Claude to react to."""
    with _lock:
        state = _load(time.time())
        result = _ACTIONS[action](state, **kwargs)
        _save(state)
        logger.bind(tag=TAG).info(f"Mochi {action}: {result}")
        return result + "\nNieuwe toestand:\n" + _describe(state)


def _eten(state, wat="iets lekkers"):
    if state["slaapt"]:
        return f"Mochi slaapt en kan nu geen {wat} eten."
    if state["verzadigd"] >= 95:
        state["plezier"] = _clamp(state["plezier"] - 3)
        return f"Mochi zit propvol en wil geen {wat} meer."
    state["verzadigd"] = _clamp(state["verzadigd"] + 30)
    state["schoon"] = _clamp(state["schoon"] - 5)
    state["band"] = _clamp(state["band"] + 1)
    return f"Mochi heeft {wat} gegeten."


def _spelen(state, spel="een spelletje"):
    if state["slaapt"]:
        return "Mochi slaapt en kan nu niet spelen."
    if state["energie"] < 15:
        return f"Mochi is te moe om {spel} te spelen."
    state["plezier"] = _clamp(state["plezier"] + 25)
    state["energie"] = _clamp(state["energie"] - 12)
    state["verzadigd"] = _clamp(state["verzadigd"] - 5)
    state["schoon"] = _clamp(state["schoon"] - 5)
    state["band"] = _clamp(state["band"] + 2)
    return f"Mochi heeft {spel} gespeeld."


def _knuffelen(state):
    state["plezier"] = _clamp(state["plezier"] + 10)
    state["band"] = _clamp(state["band"] + 3)
    return "Mochi is geknuffeld."


def _wassen(state):
    if state["slaapt"]:
        return "Mochi slaapt; wassen kan straks."
    state["schoon"] = 100
    state["plezier"] = _clamp(state["plezier"] - 2)
    state["band"] = _clamp(state["band"] + 1)
    return "Mochi is in bad geweest en is weer schoon."


def _slapen(state):
    if state["slaapt"]:
        return "Mochi sliep al."
    state["slaapt"] = True
    return "Mochi is gaan slapen."


def _wakker(state):
    if not state["slaapt"]:
        return "Mochi was al wakker."
    state["slaapt"] = False
    if state["energie"] < 50:
        state["plezier"] = _clamp(state["plezier"] - 5)
        return "Mochi is wakker gemaakt, maar is nog moe en een beetje chagrijnig."
    return "Mochi is wakker en uitgerust."


def _reageren(state, gebeurtenis):
    """Something physical happened to the device (shaken, picked up, ...)."""
    if gebeurtenis == "geschud":
        state["plezier"] = _clamp(state["plezier"] - 4)
        if state["slaapt"]:
            state["slaapt"] = False
            return "Mochi werd wakker geschud."
        return "Mochi is door elkaar geschud en is duizelig."
    if gebeurtenis == "opgepakt":
        state["plezier"] = _clamp(state["plezier"] + 3)
        state["band"] = _clamp(state["band"] + 1)
        return "Mochi is opgepakt."
    return f"Er gebeurde iets met Mochi: {gebeurtenis}."


_ACTIONS = {
    "eten": _eten, "spelen": _spelen, "knuffelen": _knuffelen, "wassen": _wassen,
    "slapen": _slapen, "wakker": _wakker, "reageren": _reageren,
}
