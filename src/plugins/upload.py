import time
import requests
import json
import os

from beet import Context

SERVER_ID = os.environ["BLOOM_SERVER_ID"]
PACK = "shulkerbox_data_pack.zip"
TARGET = f"/TheShulkerBox/datapacks/{PACK}"
URL = f"https://mc.bloom.host/api/client/servers/{SERVER_ID}/"
HEADERS = {
    "Accept": "application/json",
    "Authorization": "Bearer " + os.environ["BLOOM_API_KEY"],
}


def tellraw():
    return json.dumps(
        [
            {
                "text": "\n",
                "extra": [
                    {"text": "[", "color": "dark_purple", "bold": True},
                    {"text": " 🗡 Build Alert 🗡 ", "color": "light_purple"},
                    {"text": "]", "color": "dark_purple", "bold": True},
                    "\n",
                ],
                "click_event": {"action": "run_command", "command": "reload"},
                "hover_event": {"action": "show_text", "value": "Click to /reload"},
            },
        ]
    )


def make_request(route: str, data: dict[str, str] | str | bytes):
    if type(data) is dict:
        resp = requests.post(
            URL + route,
            data=json.dumps(data),
            headers=HEADERS | {"Content-Type": "application/json"},
        )
    else:
        resp = requests.post(URL + route, data=data, headers=HEADERS)
    resp.raise_for_status()
    print("Success", route, len(data) if route != "command" else data, resp.content)


def beet_default(ctx: Context):
    yield

    path = ctx.directory / "dist" / PACK
    ctx.data.save(path=path, overwrite=True, zipped=True)

    make_request(
        route=rf"files/write?file={TARGET.replace('/', '%2F')}",
        data=(path).read_bytes(),
    )
    time.sleep(0.05)
    make_request(route="command", data={"command": "tellraw @a[tag=op] " + tellraw()})
    make_request(route="command", data={"command": "reload"})
