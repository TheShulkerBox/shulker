from beet.toolchain.cli import beet
import beet.toolchain.commands as commands
from beet import Project
import click

@beet.command()
@click.pass_context
def deploy(ctx: click.Context):
    project = ctx.ensure_object(Project)
    project.config_path = "beet-upload.yaml"
    ctx.invoke(commands.build)
