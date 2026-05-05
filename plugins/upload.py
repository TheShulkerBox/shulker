import asyncio
from datetime import datetime
import json
import os
import subprocess

from beet import Context
import pytz

from src.lib.text import Theme
from plugins.bloom import make_request, watch_for_errors


PACK = "shulkerbox_data_pack.zip"
TARGET = f"/TheShulkerBox/datapacks/{PACK}"


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
    restart = os.environ.get("DEPLOY_RESTART") == "1"

    if restart:
        await asyncio.sleep(1.5)
        await make_request(route="power", data={"signal": "restart"})
        try:
            async with asyncio.timeout(120):
                errors = await task
        except TimeoutError:
            errors = []
    else:
        await make_request(route="command", data={"command": "reload"})

        try:
            async with asyncio.timeout(1):
                errors = await task
        except TimeoutError:
            errors = []

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
