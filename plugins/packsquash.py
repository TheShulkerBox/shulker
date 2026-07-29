"""Optimize Beet's zipped pack outputs with the PackSquash CLI."""

import json
import logging
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import tomllib
from typing import Literal

from beet import Context, PluginOptions
from beet.contrib.autosave import Autosave


logger = logging.getLogger("packsquash")

PackName = Literal["resource_pack", "data_pack"]
MANAGED_OPTIONS = {"pack_directory", "output_file_path"}


class PackSquashOptions(PluginOptions):
    """Options for the PackSquash output wrapper."""

    enabled: bool = True
    executable: str = "packsquash"
    options_file: str = "packsquash.toml"
    packs: list[PackName] = ["resource_pack"]


def resolve_path(ctx: Context, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ctx.directory / path


def read_options_fragment(path: Path) -> str:
    try:
        contents = path.read_text()
    except OSError as exc:
        raise RuntimeError(f"Could not read PackSquash options file {path}.") from exc

    try:
        options = tomllib.loads(contents)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"Invalid PackSquash options file {path}: {exc}") from exc

    managed = MANAGED_OPTIONS.intersection(options)
    if managed:
        names = ", ".join(sorted(managed))
        raise RuntimeError(
            f"Remove {names} from {path}; the Beet wrapper sets those options."
        )

    return contents


def make_options(pack_directory: Path, output_path: Path, fragment: str) -> str:
    """Prepend wrapper-managed paths to the user-editable options fragment."""
    return (
        f"pack_directory = {json.dumps(str(pack_directory))}\n"
        f"output_file_path = {json.dumps(str(output_path))}\n\n"
        f"{fragment}"
    )


def optimize_pack(
    ctx: Context,
    pack_name: PackName,
    executable: Path,
    options_fragment: str,
):
    pack = ctx.assets if pack_name == "resource_pack" else ctx.data

    if not pack.zipped:
        raise RuntimeError(
            f"PackSquash target {pack_name!r} isn't zipped in the Beet configuration."
        )
    if ctx.output_directory is None:
        raise RuntimeError("PackSquash requires Beet's output directory to be set.")

    output_path = ctx.output_directory / f"{pack.name}.zip"
    before_size = output_path.stat().st_size if output_path.is_file() else None

    ctx.output_directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{pack.name}-packsquash-", dir=ctx.output_directory
    ) as temporary_directory:
        temporary_path = Path(temporary_directory)
        pack_directory = temporary_path / "pack"
        optimized_path = temporary_path / f"{pack.name}.zip"
        options_path = temporary_path / "packsquash.toml"

        pack_directory.mkdir()
        pack.dump(pack_directory)
        options_path.write_text(
            make_options(pack_directory, optimized_path, options_fragment)
        )

        logger.info("Optimizing %s with PackSquash.", pack.name)
        result = subprocess.run(
            [
                str(executable),
                "--no-color",
                "--no-emoji",
                str(options_path),
            ],
            cwd=ctx.directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(
                f"PackSquash failed while optimizing {pack.name} "
                f"(exit code {result.returncode}).\n{result.stdout.rstrip()}"
            )

        for line in result.stdout.splitlines():
            if line.startswith("!"):
                logger.warning("%s", line)
            elif line.startswith("#"):
                logger.info("%s", line)

        if not optimized_path.is_file():
            raise RuntimeError(
                f"PackSquash succeeded but didn't create {optimized_path}."
            )

        optimized_size = optimized_path.stat().st_size
        os.replace(optimized_path, output_path)

    if before_size is None:
        print(f"PackSquash wrote {output_path.name}: {optimized_size:,} bytes")
    else:
        reduction = 1 - optimized_size / before_size
        print(
            f"PackSquash optimized {output_path.name}: "
            f"{before_size:,} -> {optimized_size:,} bytes "
            f"({reduction:.1%} smaller)"
        )


def run_packsquash(ctx: Context):
    opts = ctx.validate("packsquash", PackSquashOptions)
    if not opts.enabled:
        return

    executable = resolve_path(ctx, opts.executable)
    options_file = resolve_path(ctx, opts.options_file)

    if not executable.is_file():
        raise RuntimeError(f"PackSquash executable not found at {executable}.")
    if not os.access(executable, os.X_OK):
        raise RuntimeError(f"PackSquash executable isn't executable: {executable}.")

    options_fragment = read_options_fragment(options_file)
    for pack_name in opts.packs:
        optimize_pack(ctx, pack_name, executable, options_fragment)


def beet_default(ctx: Context):
    """Run PackSquash after Beet's standard output handler."""
    opts = ctx.validate("packsquash", PackSquashOptions)
    if opts.enabled:
        ctx.inject(Autosave).add_output(run_packsquash)
