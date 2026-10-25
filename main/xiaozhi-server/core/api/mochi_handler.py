import json

from aiohttp import web

from core.utils import mochi_pet


async def handle_state(request: web.Request) -> web.Response:
    """GET /mochi/state[?claim=1]: Mochi's state for the device's face and need bars.

    claim=1 means the device is idle and may start a conversation; a returned
    `aandacht` reason is then marked as used on the server.
    """
    claim = request.query.get("claim") == "1"
    state = mochi_pet.device_state(claim_attention=claim)
    return web.json_response(state, dumps=lambda obj: json.dumps(obj, ensure_ascii=False))
