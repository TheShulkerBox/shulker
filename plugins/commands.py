from beet.toolchain.cli import beet
import beet.toolchain.commands as commands
from beet import Project
import click


@beet.command()
@click.option("--restart", "-r", is_flag=True, help="Restart the server instead of reloading")
@click.pass_context
def deploy(ctx: click.Context, restart: bool):
    import os
    if restart:
        os.environ["DEPLOY_RESTART"] = "1"
    project = ctx.ensure_object(Project)
    project.config_path = "beet-upload.yaml"
    ctx.invoke(commands.build)


@beet.command()
def logs():
    import asyncio
    from plugins.bloom import make_request, watch_for_errors
    
    async def watch():
        resp = await make_request("websocket")
        data = resp.json()["data"]
        await watch_for_errors(data["socket"], data["token"])
        
    asyncio.run(watch())
