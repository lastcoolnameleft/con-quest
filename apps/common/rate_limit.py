from __future__ import annotations

from django.core.cache import cache
from django.http import JsonResponse


def client_identifier(request) -> str:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def check_rate_limit(*, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
    """Return (allowed, retry_after_seconds, current_count)."""
    count = cache.get(key, 0)
    if count >= limit:
        return False, window_seconds, count

    cache.add(key, 0, timeout=window_seconds)
    new_count = cache.incr(key)
    return True, 0, new_count


def add_rate_limit_headers(response, *, limit: int, window_seconds: int, remaining: int, retry_after: int = 0):
    response["X-RateLimit-Limit"] = str(limit)
    response["X-RateLimit-Remaining"] = str(max(0, remaining))
    response["X-RateLimit-Window"] = str(window_seconds)
    if retry_after > 0:
        response["Retry-After"] = str(retry_after)
    return response


def rate_limited_json_response(
    *,
    limit: int,
    window_seconds: int,
    retry_after: int,
    message: str,
    extra_payload: dict | None = None,
) -> JsonResponse:
    payload = {
        "error": "rate_limited",
        "message": message,
        "retry_after_seconds": retry_after,
    }
    if extra_payload:
        payload.update(extra_payload)

    response = JsonResponse(payload, status=429)
    return add_rate_limit_headers(
        response,
        limit=limit,
        window_seconds=window_seconds,
        remaining=0,
        retry_after=retry_after,
    )
