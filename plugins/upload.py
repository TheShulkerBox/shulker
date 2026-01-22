import asyncio
from datetime import datetime
import re
import dotenv
import json
import os
import httpx
import subprocess

from beet import Context
import pytz
import rich
from websockets.asyncio.client import connect

from src.lib.text import Theme


dotenv.load_dotenv()


SERVER_ID = os.environ["BLOOM_SERVER_ID"]
PACK = "shulkerbox_data_pack.zip"
TARGET = f"/TheShulkerBox/datapacks/{PACK}"
URL = f"https://mc.bloom.host/api/client/servers/{SERVER_ID}/"
HEADERS = {
    "Accept": "application/json",
    "Authorization": "Bearer " + os.environ["BLOOM_API_KEY"],
}
ERROR_PATTERN = re.compile(r"\[\d\d:\d\d:\d\d\] \[Server thread/ERROR\]: (.+)")


def get_git_user() -> str:
    """Returns the git user name."""
    try:
        user = (
            subprocess.check_output(["git", "config", "user.name"])
            .decode("utf-8")
            .strip()
        )
        if user:
            return user
    except subprocess.CalledProcessError:
        pass

    return "Unknown"


def tellraw():
    user = get_git_user()
    local_tz = pytz.timezone("EST")
    now = datetime.now(local_tz)
    human_time = now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
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
                "hover_event": {
                    "action": "show_text",
                    "value": f"From {user}\n{human_time}",
                },
            },
        ]
    )


async def make_request(
    route: str,
    data: dict[str, str] | str | bytes | None = None,
):
    url = URL + route
    headers = HEADERS | {"Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        if data is None:
            resp = await client.get(url, headers=headers)
        elif isinstance(data, dict):
            resp = await client.post(url, content=json.dumps(data), headers=headers)
        else:
            resp = await client.post(url, content=data, headers=HEADERS)
        resp.raise_for_status()
        print(
            "Success",
            route,
            (len(data) if route != "command" else data) if data is not None else "",
            resp.content if route != "websocket" else "",
        )
        return resp


async def watch_for_errors(url: str, token: str):
    errors = []
    try:
        async with connect(
            url, additional_headers={"Origin": "https://mc.bloom.host"}
        ) as websocket:
            print("WebSocket connection established")

            # Authenticate with the server
            auth_message = {"event": "auth", "args": [token]}
            await websocket.send(json.dumps(auth_message))

            # Listen for messages
            async for message in websocket:
                if (data := json.loads(message)) and (
                    data["event"] == "console output"
                ):
                    for arg in data["args"]:
                        rich.print(arg)
                        if "Server thread/ERROR" in arg:
                            errors.append(ERROR_PATTERN.match(arg).group(1).strip())

    except Exception as err:
        print(err)
    finally:
        return errors


async def push_to_server(path: str):
    resp = await make_request("websocket")
    data = resp.json()["data"]
    task = asyncio.create_task(watch_for_errors(data["socket"], data["token"]))
    await make_request(
        route=rf"files/write?file={TARGET.replace('/', '%2F')}",
        data=(path).read_bytes(),
    )
    await asyncio.sleep(0.1)
    await make_request(
        route="command", data={"command": "tellraw @a[tag=op] " + tellraw()}
    )
    await make_request(route="command", data={"command": "reload"})

    async with asyncio.timeout(1):
        errors = await task

    if errors:
        msg = [{"text": "\n" + error, "color": Theme.Failure} for error in errors]
        await make_request(
            route="command", data={"command": f"tellraw @a[tag=op] {json.dumps(msg)}"}
        )


def beet_default(ctx: Context):
    yield

    if ctx.meta["deploy"]:
        path = ctx.directory / "dist" / PACK
        ctx.data.save(path=path, overwrite=True, zipped=True)

        asyncio.run(push_to_server(path))
