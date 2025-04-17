# shulker

## Setup

The only requirement for getting started is [`uv`](https://docs.astral.sh/uv/), which will handle installing and running the correct python alongside handling all of the project dependencies.

```bash
uv install
```

## Building

We use [beet](https://mcbeet.dev/) to manage building our packs for release.

```bash
uv run beet
```

## Push to Server

This requires a valid bloom key