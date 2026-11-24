"""The JSON body of a request as a plain dict: a body that is no JSON, or no object, is an empty one (the route then answers with its own refusal)."""

from __future__ import annotations

from fastapi import Request


async def json_dict(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:  # includes a body that is not valid JSON or not valid UTF-8
        return {}
    return body if isinstance(body, dict) else {}
