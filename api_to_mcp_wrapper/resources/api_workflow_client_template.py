"""Production Async API Workflow Client Template for API-to-MCP Servers on Cloud Run.

Provides:
1. Multi-Tenant Auth Header Injection:
   - Automatically forwards the caller's 3-Legged OAuth Bearer token (`get_current_user_token()`)
     for per-user tenant isolation, with optional fallback to a Secret Manager API key (`DOWNSTREAM_API_KEY`).
2. Connection Pooling, Timeouts & Exponential Backoff Retries (`httpx.AsyncClient`).
3. Built-in Circuit Breaker to fail fast and return structured fallback messages when a downstream API degrades.
4. Bounded Parallel Fan-Out (`fan_out_gather`) to orchestrate N fine-grained REST/GraphQL endpoints concurrently
   inside a single coarse-grained MCP workflow tool.
5. Context-Window Pruner (`prune_payload_for_llm`) to strip nulls, binary/base64 blobs, and oversized arrays.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

import httpx

logger = logging.getLogger("mcp-api-workflow-client")


class CircuitBreaker:
    """Lightweight circuit breaker preventing cascading hangs when downstream partner APIs fail."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout_sec: int = 30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.state = "CLOSED"  # CLOSED | OPEN | HALF_OPEN

    def allow_request(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if (time.time() - self.last_failure_time) >= self.recovery_timeout_sec:
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning("Downstream API CircuitBreaker tripped to OPEN (failures=%d)", self.failure_count)

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_time": int(self.last_failure_time) if self.last_failure_time else None,
        }


def prune_payload_for_llm(
    data: Any,
    *,
    max_list_items: int = 25,
    max_str_len: int = 1500,
    drop_keys: Optional[set[str]] = None,
) -> Any:
    """Recursively prunes verbose downstream API JSON payloads so they stay compact for LLM context windows."""
    ignored = drop_keys or {"raw_binary", "base64_content", "_links", "etag", "internal_trace_id"}

    if isinstance(data, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in data.items():
            if k in ignored or v is None or v == "" or v == [] or v == {}:
                continue
            cleaned[k] = prune_payload_for_llm(
                v,
                max_list_items=max_list_items,
                max_str_len=max_str_len,
                drop_keys=ignored,
            )
        return cleaned

    if isinstance(data, list):
        total = len(data)
        sliced = [
            prune_payload_for_llm(
                item,
                max_list_items=max_list_items,
                max_str_len=max_str_len,
                drop_keys=ignored,
            )
            for item in data[:max_list_items]
        ]
        if total > max_list_items:
            sliced.append({"_truncated_notice": f"Showing {max_list_items} of {total} total items."})
        return sliced

    if isinstance(data, str) and len(data) > max_str_len:
        return data[:max_str_len] + f"... [truncated {len(data) - max_str_len} chars]"

    return data


class DownstreamApiClient:
    """Async HTTP workflow client for wrapping fine-grained REST / GraphQL APIs into coarse-grained MCP tools."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        user_token_getter: Optional[Callable[[], Optional[str]]] = None,
        fallback_api_key_env: str = "DOWNSTREAM_API_KEY",
        timeout_sec: float = 15.0,
        max_concurrency: int = 6,
    ):
        self.base_url = (base_url or os.environ.get("DOWNSTREAM_API_BASE_URL", "")).rstrip("/")
        self.user_token_getter = user_token_getter
        self.fallback_api_key_env = fallback_api_key_env
        self.timeout_sec = timeout_sec
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.circuit_breaker = CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_sec, connect=5.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
                follow_redirects=True,
            )
        return self._client

    def _build_auth_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Builds outbound headers preferring the authenticated user's 3LO Bearer token over static API keys."""
        headers: Dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "GoogleCloudRun-MCP-WorkflowClient/1.0",
        }
        user_token = self.user_token_getter() if self.user_token_getter else None
        fallback_key = os.environ.get(self.fallback_api_key_env, "").strip()

        # 1. Multi-tenant 3-Legged OAuth passthrough (when token is an upstream OAuth token)
        if user_token and not user_token.startswith("mcp_at."):
            headers["Authorization"] = f"Bearer {user_token}"
        # 2. Fallback to Secret Manager / ENV service API key (or custom header)
        elif fallback_key:
            auth_header_name = os.environ.get("DOWNSTREAM_API_KEY_HEADER", "Authorization").strip()
            if auth_header_name.lower() == "authorization" and not fallback_key.lower().startswith(("bearer ", "basic ", "apikey ")):
                headers["Authorization"] = f"Bearer {fallback_key}"
            else:
                headers[auth_header_name] = fallback_key

        if extra_headers:
            headers.update(extra_headers)
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        retries: int = 2,
    ) -> Dict[str, Any]:
        """Executes a resilient async HTTP call with circuit breaking, retries, and structured error handling."""
        if not self.circuit_breaker.allow_request():
            return {
                "error": "circuit_breaker_open",
                "message": "Downstream API is temporarily unavailable (circuit breaker open).",
                "circuit_breaker": self.circuit_breaker.get_status(),
            }

        client = await self._get_client()
        merged_headers = self._build_auth_headers(headers)
        clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}

        last_err: Optional[str] = None
        for attempt in range(retries + 1):
            try:
                async with self.semaphore:
                    resp = await client.request(
                        method.upper(),
                        path,
                        params=clean_params,
                        json=json_body,
                        headers=merged_headers,
                    )
                if resp.status_code in (429, 502, 503, 504) and attempt < retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue

                if resp.status_code >= 500:
                    self.circuit_breaker.record_failure()
                else:
                    self.circuit_breaker.record_success()

                if resp.status_code >= 400:
                    return {
                        "error": f"http_{resp.status_code}",
                        "status_code": resp.status_code,
                        "path": path,
                        "detail": resp.text[:500],
                    }

                return resp.json() if resp.content else {"status": "ok"}
            except Exception as exc:
                last_err = str(exc)
                if attempt < retries:
                    await asyncio.sleep(0.4 * (2 ** attempt))
                else:
                    self.circuit_breaker.record_failure()

        return {
            "error": "request_failed",
            "path": path,
            "message": last_err or "Unknown upstream error",
        }

    async def fan_out_gather(
        self,
        tasks: Dict[str, Awaitable[Any]],
    ) -> Dict[str, Any]:
        """Executes multiple named downstream API coroutines concurrently and returns a keyed dictionary.

        Example inside a coarse-grained `@mcp.tool()`:
             composite = await api_client.fan_out_gather({
                 "profile": api_client.request("GET", f"/v1/customers/{cid}"),
                 "recent_orders": api_client.request("GET", f"/v1/customers/{cid}/orders", params={"limit": 5}),
                 "open_tickets": api_client.request("GET", "/v1/tickets", params={"customer_id": cid, "status": "open"}),
             })
        """
        keys = list(tasks.keys())
        coros = [tasks[k] for k in keys]
        results = await asyncio.gather(*coros, return_exceptions=True)
        combined: Dict[str, Any] = {}
        for k, res in zip(keys, results):
            if isinstance(res, Exception):
                combined[k] = {"error": str(res)}
            else:
                combined[k] = res
        return combined

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
