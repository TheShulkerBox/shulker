import os
import json
import re
import httpx
import rich
from websockets.asyncio.client import connect
import dotenv

dotenv.load_dotenv()

SERVER_ID = os.environ.get("BLOOM_SERVER_ID")
BLOOM_API_KEY = os.environ.get("BLOOM_API_KEY")
ERROR_PATTERN = re.compile(r"\[\d\d:\d\d:\d\d\] \[Server thread/ERROR\]: (.+)")

def create_url() -> str:
    if not SERVER_ID:
        raise ValueError("BLOOM_SERVER_ID environment variable not set")
    return f"https://mc.bloom.host/api/client/servers/{SERVER_ID}/"

def create_headers() -> dict[str, str]:
    if not BLOOM_API_KEY:
        raise ValueError("BLOOM_API_KEY environment variable not set")
    return {
        "Accept": "application/json",
        "Authorization": "Bearer " + BLOOM_API_KEY,
    }

async def make_request(
    route: str,
    data: dict[str, str] | str | bytes | None = None,
):
    url = create_url() + route
    headers = create_headers() | {"Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=30.0)) as client:
        if data is None:
            resp = await client.get(url, headers=headers)
        elif isinstance(data, dict):
            resp = await client.post(url, content=json.dumps(data), headers=headers)
        else:
            resp = await client.post(url, content=data, headers=create_headers())
        resp.raise_for_status()
        print(
            "Success",
            route,
            (len(data) if route != "command" else data) if data is not None else "",
            resp.content if route != "websocket" else "",
        )
        return resp

async def watch_for_errors(url: str, token: str) -> list[str]:
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
    
    return errors
