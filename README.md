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

## Push to Bloom

First, you'll need to grab a bloom api key and your server id and set it to the following environment variables:
- `BLOOM_API_KEY`
- `BLOOM_SERVER_ID`

Then,
```bash
uv run beet upload
```
