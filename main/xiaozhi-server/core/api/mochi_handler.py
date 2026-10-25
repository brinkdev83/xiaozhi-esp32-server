import json

from aiohttp import web

from core.utils import mochi_pet


def _json(obj, status=200):
    return web.json_response(obj, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


async def handle_state(request: web.Request) -> web.Response:
    """GET /mochi/state[?claim=1]: Mochi's state for the device's face and need bars.

    claim=1 means the device is idle and may start a conversation; a returned
    `aandacht` reason is then marked as used on the server.
    """
    claim = request.query.get("claim") == "1"
    return _json(mochi_pet.device_state(claim_attention=claim))


async def handle_name(request: web.Request) -> web.Response:
    """POST /mochi/naam with {"naam": "..."}: rename the pet from the device's name screen."""
    try:
        body = await request.json()
        name = mochi_pet.set_name(body.get("naam", ""))
    except (ValueError, json.JSONDecodeError, AttributeError):
        return _json({"fout": "ongeldige naam"}, status=400)
    return _json({"naam": name})
