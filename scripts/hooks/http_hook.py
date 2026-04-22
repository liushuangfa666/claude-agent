"""
HttpHook - HTTP Webhook Hook
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
from dataclasses import dataclass

import httpx

from .enhanced import Hook, HookResult

logger = logging.getLogger(__name__)


ENV_VAR_PATTERN = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")


@dataclass
class HttpHookConfig:
    url: str
    method: str = "POST"
    headers: dict | None = None
    timeout: float = 10.0
    retry_count: int = 0
    retry_delay: float = 1.0
    verify_ssl: bool = True
    secret: str | None = None
    signature_header: str = "X-Webhook-Signature"
    signature_algorithm: str = "sha256"


class HttpHook(Hook):
    """HTTP Webhook Hook - 异步通知"""

    def __init__(
        self,
        callback: str | None = None,
        method: str = "POST",
        headers: dict | None = None,
        timeout: float = 10.0,
        retry_count: int = 0,
        verify_ssl: bool = True,
        secret: str | None = None,
        signature_header: str = "X-Webhook-Signature",
        signature_algorithm: str = "sha256",
    ):
        super().__init__("Notification", callback)
        self.method = method.upper()
        self.headers = headers or {}
        self.timeout = timeout
        self.retry_count = retry_count
        self.verify_ssl = verify_ssl
        self.secret = secret
        self.signature_header = signature_header
        self.signature_algorithm = signature_algorithm

    def _interpolate_env_vars(self, text: str) -> str:
        def replace_env_var(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        return ENV_VAR_PATTERN.sub(replace_env_var, text)

    def _interpolate_context(self, text: str, context: dict) -> str:
        def replace_context(match):
            key = match.group(1)
            value = context.get(key, match.group(0))
            return str(value)
        pattern = re.compile(r"\$\{\{([^}]+)\}\}")
        return pattern.sub(replace_context, text)

    def _prepare_url(self, context: dict) -> str:
        url = self.callback
        url = self._interpolate_env_vars(url)
        url = self._interpolate_context(url, context)
        return url

    def _prepare_headers(self, context: dict) -> dict:
        headers = {}
        for key, value in self.headers.items():
            value = self._interpolate_env_vars(str(value))
            value = self._interpolate_context(value, context)
            headers[key] = value
        return headers

    def _prepare_body(self, context: dict) -> dict:
        return {
            "event": context.get("event", "unknown"),
            "timestamp": context.get("timestamp", ""),
            "session_id": context.get("session_id", ""),
            "data": context,
        }

    def _generate_signature(self, body: str) -> str:
        """Generate HMAC signature for the request body."""
        if not self.secret:
            return ""

        if self.signature_algorithm == "sha256":
            signature = hmac.new(
                self.secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
        elif self.signature_algorithm == "sha1":
            signature = hmac.new(
                self.secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha1
            ).hexdigest()
        else:
            signature = hmac.new(
                self.secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()

        return f"{self.signature_algorithm}={signature}"

    @staticmethod
    def verify_signature(
        body: bytes,
        signature: str,
        secret: str,
        algorithm: str = "sha256",
    ) -> bool:
        """
        Verify webhook signature.
        
        Args:
            body: Raw request body
            signature: Signature from header
            secret: Shared secret
            algorithm: Hash algorithm (sha256 or sha1)
        
        Returns:
            True if signature is valid
        """
        if not signature or not secret:
            return False

        expected = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256 if algorithm == "sha256" else hashlib.sha1
        ).hexdigest()

        expected_sig = f"{algorithm}={expected}"
        return hmac.compare_digest(expected_sig, signature)

    async def execute(self, context: dict) -> HookResult:
        if not self._enabled:
            return HookResult(hook_name=self.name, success=True, message="disabled")

        if not self.callback:
            return HookResult(hook_name=self.name, success=True, message="no webhook URL configured")

        import time
        start = time.time()

        try:
            url = self._prepare_url(context)
            headers = self._prepare_headers(context)
            body_dict = self._prepare_body(context)
            body_json = json.dumps(body_dict, ensure_ascii=False)

            # Add signature header if secret is configured
            if self.secret:
                signature = self._generate_signature(body_json)
                headers[self.signature_header] = signature

            last_error = None

            for attempt in range(self.retry_count + 1):
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        if self.method == "GET":
                            response = await client.get(url, headers=headers, params=body_dict, verify=self.verify_ssl)
                        elif self.method == "POST":
                            response = await client.post(url, headers=headers, content=body_json, verify=self.verify_ssl)
                        elif self.method == "PUT":
                            response = await client.put(url, headers=headers, content=body_json, verify=self.verify_ssl)
                        elif self.method == "DELETE":
                            response = await client.delete(url, headers=headers, verify=self.verify_ssl)
                        else:
                            return HookResult(hook_name=self.name, success=False, error=f"Unsupported HTTP method: {self.method}")

                    if response.status_code < 400:
                        duration_ms = int((time.time() - start) * 1000)
                        return HookResult(
                            hook_name=self.name,
                            success=True,
                            message=f"HTTP {response.status_code}: {response.text[:200]}",
                            duration_ms=duration_ms,
                        )
                    else:
                        last_error = f"HTTP {response.status_code}: {response.text[:200]}"

                except httpx.TimeoutException:
                    last_error = f"Request timeout after {self.timeout}s"
                except Exception as e:
                    last_error = str(e)

                if attempt < self.retry_count:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

            duration_ms = int((time.time() - start) * 1000)
            return HookResult(
                hook_name=self.name,
                success=False,
                error=f"Webhook failed after {self.retry_count + 1} attempts: {last_error}",
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"HttpHook execution failed: {e}")
            duration_ms = int((time.time() - start) * 1000)
            return HookResult(hook_name=self.name, success=False, error=str(e), duration_ms=duration_ms)


def load_http_hooks_from_config(config: dict) -> list[HttpHook]:
    """从配置字典加载 HTTP Hook

    配置格式:
    {
        "http_hooks": [
            {
                "url": "https://example.com/webhook",
                "method": "POST",
                "headers": {"Authorization": "Bearer token"},
                "timeout": 10.0,
                "retry_count": 3,
                "event": "PostToolUse",  // 可选，触发条件
                "secret": "webhook_secret",  // 可选，签名密钥
                "signature_header": "X-Webhook-Signature",  // 可选，签名头
                "signature_algorithm": "sha256"  // 可选，sha256 或 sha1
            },
            ...
        ]
    }
    """
    hooks = []
    http_hooks = config.get("http_hooks", [])

    for hook_config in http_hooks:
        hook = HttpHook(
            callback=hook_config.get("url"),
            method=hook_config.get("method", "POST"),
            headers=hook_config.get("headers", {}),
            timeout=hook_config.get("timeout", 10.0),
            retry_count=hook_config.get("retry_count", 0),
            secret=hook_config.get("secret"),
            signature_header=hook_config.get("signature_header", "X-Webhook-Signature"),
            signature_algorithm=hook_config.get("signature_algorithm", "sha256"),
        )

        # 设置触发条件
        if hook_config.get("event"):
            hook.condition = hook_config["event"]

        hooks.append(hook)

    return hooks
