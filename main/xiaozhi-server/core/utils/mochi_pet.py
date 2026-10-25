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

# Growth: stage by age in hours (an egg hatches after its first hour).
STAGES = (("ei", 0), ("baby", 1), ("kind", 48), ("volwassen", 144))
STAGE_STYLE = {
    "ei": "Je bent nog een ei. Je kunt alleen zacht piepen en tikken, een paar klanken; "
          "warmte (knuffelen) vind je fijn. Eten, spelen en wassen kan nog niet.",
    "baby": "Je bent een baby: korte zinnetjes van een paar woorden, kinderlijk, "
            "nieuwsgierig, je verwart soms woorden.",
    "kind": "Je bent een kind: speels en vol vragen, eenvoudige zinnen, grapjes.",
    "volwassen": "Je bent volwassen: nog steeds lief en speels, maar wijzer; je praat in "
                 "gewone zinnen en vertelt soms wat je hebt meegemaakt.",
}

# Asking for attention by itself: only by day, and not too often.
ATTENTION_BELOW = 30
ATTENTION_EVERY_S = 45 * 60
DAY_HOURS = range(8, 22)
ATTENTION_REASON = {
    "verzadigd": "honger", "energie": "moe", "plezier": "verveling", "schoon": "vies",
}

_lock = threading.Lock()


def _new_state(now):
    return {
        "verzadigd": 80, "energie": 80, "plezier": 80, "schoon": 90,
        "band": 10, "slaapt": False, "geboren": now, "bijgewerkt": now,
        "fase": "ei", "fase_sinds": now, "laatste_aandacht": 0,
    }


def _stage_for(state):
    hours = (state["bijgewerkt"] - state["geboren"]) / 3600
    stage = STAGES[0][0]
    for name, from_hours in STAGES:
        if hours >= from_hours:
            stage = name
    return stage


def _clamp(value):
    return max(0, min(100, round(value, 1)))


def _load(now):
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = _new_state(now)
    hours = min(max(0.0, (now - state["bijgewerkt"]) / 3600), MAX_CATCH_UP_HOURS)
    if state.get("fase", "baby") != "ei":  # an egg has no needs yet
        drift = ASLEEP_DRIFT if state["slaapt"] else AWAKE_DRIFT
        for need in NEEDS:
            state[need] = _clamp(state[need] + drift[need] * hours)
        if state["slaapt"] and state["energie"] >= 100:
            state["slaapt"] = False  # uitgeslapen
        # Neglect wears the bond down a little.
        if any(state[n] < LOW for n in NEEDS):
            state["band"] = _clamp(state["band"] - hours)
    state["bijgewerkt"] = now
    # Growth (older state files have no stage yet).
    state.setdefault("laatste_aandacht", 0)
    stage = _stage_for(state)
    if "fase" not in state:
        state["fase"], state["fase_sinds"] = stage, state["geboren"]
    elif state["fase"] != stage:
        logger.bind(tag=TAG).info(f"Mochi groeit: {state['fase']} -> {stage}")
        state["fase"], state["fase_sinds"] = stage, now
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
    stage = state["fase"]
    lines = [f"Fase: {stage}. {STAGE_STYLE[stage]}"]
    if state["bijgewerkt"] - state["fase_sinds"] < 2 * 3600 and state["fase_sinds"] > state["geboren"]:
        lines.append(f"Je bent net een {stage} geworden; daar ben je trots of verbaasd over.")
    if stage == "ei":
        lines.append(f"Band met de gebruiker: {state['band']:.0f}/100.")
        return "\n".join(lines)
    parts = [f"{n}: {state[n]:.0f}/100 ({_word(n, state[n])})" for n in NEEDS]
    lines += [
        "Mochi slaapt nu." if state["slaapt"] else "Mochi is wakker.",
        "; ".join(parts) + ".",
        f"Band met de gebruiker: {state['band']:.0f}/100. Leeftijd: {age_days} dagen.",
    ]
    if stage == "volwassen":
        lines.append("Door de goede zorg ben je lief en dankbaar." if state["band"] >= 50
                     else "Je bent wat eigenwijs geworden omdat er niet altijd voor je gezorgd werd.")
    low = [n for n in NEEDS if state[n] < LOW]
    if low:
        lines.append("Dringend: " + ", ".join(low) + " is laag; laat dat merken.")
    return "\n".join(lines)


def _mood(state):
    if state["fase"] == "ei":
        return "ei"
    if state["slaapt"]:
        return "slaapt"
    lowest = min(NEEDS, key=lambda n: state[n])
    if state[lowest] < LOW:
        return ATTENTION_REASON[lowest]
    return "blij" if state["plezier"] >= 60 else "gewoon"


def _attention(state, now):
    """Reason to call the user, or None. Records the call so it is not repeated soon."""
    if state["fase"] == "ei" or state["slaapt"]:
        return None
    if time.localtime(now).tm_hour not in DAY_HOURS:
        return None
    if now - state["laatste_aandacht"] < ATTENTION_EVERY_S:
        return None
    lowest = min(NEEDS, key=lambda n: state[n])
    if state[lowest] >= ATTENTION_BELOW:
        return None
    state["laatste_aandacht"] = now
    return ATTENTION_REASON[lowest]


def status_text():
    """Current state as Dutch text for the system prompt."""
    with _lock:
        state = _load(time.time())
        _save(state)
        return _describe(state)


def device_state(claim_attention=False):
    """Compact state for the device's face and need bars.

    With claim_attention the device is idle and may start a conversation; the
    returned `aandacht` reason is then marked as used.
    """
    with _lock:
        now = time.time()
        state = _load(now)
        reason = _attention(state, now) if claim_attention else None
        _save(state)
        if reason:
            logger.bind(tag=TAG).info(f"Mochi vraagt aandacht: {reason}")
        return {
            "fase": state["fase"],
            "slaapt": state["slaapt"],
            "stemming": _mood(state),
            "band": round(state["band"]),
            **{n: round(state[n]) for n in NEEDS},
            "aandacht": reason,
        }


def apply(action, **kwargs):
    """Apply a care action; returns a Dutch result for Claude to react to."""
    with _lock:
        state = _load(time.time())
        if state["fase"] == "ei" and action not in ("knuffelen", "reageren"):
            result = "Mochi is nog een ei; dat kan pas als hij is uitgekomen. Warm houden (knuffelen) helpt wel."
        else:
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


def _tv_kijken(state):
    if state["slaapt"]:
        return "Mochi slaapt; tv kijken kan straks."
    state["plezier"] = _clamp(state["plezier"] + 12)
    state["energie"] = _clamp(state["energie"] + 3)  # lekker hangen op de bank
    state["band"] = _clamp(state["band"] + 1)
    return "Mochi heeft samen tv gekeken op de bank."


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
    "eten": _eten, "spelen": _spelen, "tv": _tv_kijken, "knuffelen": _knuffelen, "wassen": _wassen,
    "slapen": _slapen, "wakker": _wakker, "reageren": _reageren,
}
