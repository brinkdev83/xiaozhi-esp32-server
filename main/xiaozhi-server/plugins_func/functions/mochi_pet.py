"""Care tools for Mochi, the voice pet (state in core/utils/mochi_pet.py)."""

from core.utils import mochi_pet
from plugins_func.register import register_function, ToolType, ActionResponse, Action


def _desc(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


def _result(action, **kwargs):
    return ActionResponse(Action.REQLLM, mochi_pet.apply(action, **kwargs), None)


@register_function("mochi_eten", _desc(
    "mochi_eten",
    "Mochi krijgt eten van de gebruiker. Gebruik dit wanneer de gebruiker Mochi iets te eten "
    "of te drinken geeft (bijvoorbeeld 'hier is een appel').",
    {"wat": {"type": "string", "description": "Wat Mochi krijgt, bijvoorbeeld 'een appel'."}},
    ["wat"],
), ToolType.WAIT)
def mochi_eten(wat="iets lekkers"):
    return _result("eten", wat=wat)


@register_function("mochi_spelen", _desc(
    "mochi_spelen",
    "De gebruiker speelt een spelletje met Mochi (bijvoorbeeld verstoppertje, raadsels, zingen). "
    "Kost Mochi energie, geeft plezier.",
    {"spel": {"type": "string", "description": "Welk spel, bijvoorbeeld 'verstoppertje'."}},
    ["spel"],
), ToolType.WAIT)
def mochi_spelen(spel="een spelletje"):
    return _result("spelen", spel=spel)


@register_function("mochi_tv_kijken", _desc(
    "mochi_tv_kijken",
    "Mochi kijkt samen met de gebruiker tv op de bank in de woonkamer. Ontspannend: "
    "geeft plezier zonder energie te kosten.",
), ToolType.WAIT)
def mochi_tv_kijken():
    return _result("tv")


@register_function("mochi_knuffelen", _desc(
    "mochi_knuffelen",
    "De gebruiker knuffelt, aait of troost Mochi.",
), ToolType.WAIT)
def mochi_knuffelen():
    return _result("knuffelen")


@register_function("mochi_wassen", _desc(
    "mochi_wassen",
    "De gebruiker wast Mochi of geeft Mochi een bad.",
), ToolType.WAIT)
def mochi_wassen():
    return _result("wassen")


@register_function("mochi_slapen", _desc(
    "mochi_slapen",
    "Mochi gaat slapen, bijvoorbeeld als de gebruiker welterusten zegt of Mochi naar bed stuurt.",
), ToolType.WAIT)
def mochi_slapen():
    return _result("slapen")


@register_function("mochi_wakker", _desc(
    "mochi_wakker",
    "Mochi wordt wakker gemaakt. Gebruik dit als Mochi slaapt en de gebruiker hem wakker maakt "
    "of iets met hem wil doen.",
), ToolType.WAIT)
def mochi_wakker():
    return _result("wakker")


@register_function("mochi_gebeurtenis", _desc(
    "mochi_gebeurtenis",
    "Er gebeurde iets lichamelijks met Mochi's apparaatje. Gebruik dit wanneer een bericht "
    "tussen vierkante haken meldt dat Mochi is geschud of opgepakt.",
    {"gebeurtenis": {"type": "string", "enum": ["geschud", "opgepakt"]}},
    ["gebeurtenis"],
), ToolType.WAIT)
def mochi_gebeurtenis(gebeurtenis="geschud"):
    return _result("reageren", gebeurtenis=gebeurtenis)
