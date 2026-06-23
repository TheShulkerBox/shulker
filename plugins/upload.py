import asyncio
from contextlib import suppress
from datetime import datetime
import json
import os
import subprocess

from beet import Context
import httpx
import pytz

from src.lib.text import Theme
from plugins.bloom import make_request, watch_for_errors


PACK = "shulkerbox_data_pack.zip"
TARGET = f"/TheShulkerBox/datapacks/{PACK}"
RELOAD_LOG_TIMEOUT = 10


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


def is_bad_gateway(err: Exception) -> bool:
    return (
        isinstance(err, httpx.HTTPStatusError)
        and err.response.status_code == httpx.codes.BAD_GATEWAY
    )


async def wait_for_server_startup():
    last_err: Exception | None = None

    for _ in range(12):
        await asyncio.sleep(5)

        try:
            await make_request("websocket")
            return
        except Exception as err:
            if not is_bad_gateway(err):
                raise

            last_err = err

    if last_err:
        raise last_err


async def recover_from_bad_gateway():
    print("Bloom returned 502 Bad Gateway. Starting server and retrying deploy...")
    await make_request(route="power", data={"signal": "start"})
    await wait_for_server_startup()


async def push_to_server_once(path: str):
    resp = await make_request("websocket")
    data = resp.json()["data"]
    task = asyncio.create_task(watch_for_errors(data["socket"], data["token"]))

    try:
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
                async with asyncio.timeout(RELOAD_LOG_TIMEOUT):
                    errors = await task
            except TimeoutError:
                errors = []

        if errors:
            msg = [{"text": "\n" + error, "color": Theme.Failure} for error in errors]
            await make_request(
                route="command",
                data={"command": f"tellraw @a[tag=op] {json.dumps(msg)}"},
            )
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def push_to_server(path: str):
    try:
        await push_to_server_once(path)
    except Exception as err:
        if not is_bad_gateway(err):
            raise

        await recover_from_bad_gateway()
        try:
            await push_to_server_once(path)
        except Exception as retry_err:
            if is_bad_gateway(retry_err):
                raise RuntimeError(
                    "Deploy still received 502 Bad Gateway after starting the server."
                ) from retry_err

            raise


def beet_default(ctx: Context):
    yield

    if ctx.meta["deploy"]:
        path = ctx.directory / "dist" / PACK
        ctx.data.save(path=path, overwrite=True, zipped=True)

        asyncio.run(push_to_server(path))
