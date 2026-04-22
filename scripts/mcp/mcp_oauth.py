"""
MCP OAuth 认证支持

提供 MCP 服务器的 OAuth 认证流程支持。

功能：
- OAuth 2.0 认证流程
- 令牌管理
- 令牌撤销
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs

logger = logging.getLogger(__name__)


@dataclass
class OAuthToken:
    """OAuth 令牌"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None
    expires_at: float | None = None

    def is_expired(self) -> bool:
        """检查令牌是否过期"""
        if self.expires_at is None:
            return False
        import time
        return time.time() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OAuthToken:
        expires_at = None
        if data.get("expires_in"):
            import time
            expires_at = time.time() + data["expires_in"]

        return cls(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in"),
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope"),
            expires_at=expires_at,
        )


@dataclass
class OAuthConfig:
    """OAuth 配置"""
    client_id: str
    authorization_url: str
    token_url: str
    client_secret: str | None = None
    redirect_uri: str = "http://localhost:8080/callback"
    scopes: list[str] = field(default_factory=list)
    state: str | None = None

    def get_authorization_url(self, state: str | None = None) -> str:
        """获取授权 URL"""
        if state is None:
            state = secrets.token_urlsafe(32)

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes) if self.scopes else "",
            "state": state,
        }
        return f"{self.authorization_url}?{urlencode(params)}"


class OAuthTokenStore:
    """OAuth 令牌存储"""

    def __init__(self, storage_dir: str | Path | None = None):
        if storage_dir is None:
            storage_dir = Path.home() / ".config" / "mcp" / "oauth"
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, OAuthToken] = {}

    def _get_token_file(self, server_name: str) -> Path:
        """获取令牌文件路径"""
        safe_name = server_name.replace("/", "_").replace("\\", "_")
        return self.storage_dir / f"{safe_name}.json"

    def save_token(self, server_name: str, token: OAuthToken) -> None:
        """保存令牌"""
        self._cache[server_name] = token

        token_file = self._get_token_file(server_name)
        with open(token_file, "w", encoding="utf-8") as f:
            json.dump(token.to_dict(), f, indent=2)

        logger.info(f"Saved OAuth token for server: {server_name}")

    def load_token(self, server_name: str) -> OAuthToken | None:
        """加载令牌"""
        if server_name in self._cache:
            return self._cache[server_name]

        token_file = self._get_token_file(server_name)
        if not token_file.exists():
            return None

        try:
            with open(token_file, encoding="utf-8") as f:
                data = json.load(f)
            token = OAuthToken.from_dict(data)
            self._cache[server_name] = token
            return token
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load token for {server_name}: {e}")
            return None

    def delete_token(self, server_name: str) -> bool:
        """删除令牌"""
        if server_name in self._cache:
            del self._cache[server_name]

        token_file = self._get_token_file(server_name)
        if token_file.exists():
            token_file.unlink()
            logger.info(f"Deleted OAuth token for server: {server_name}")
            return True
        return False

    def has_token(self, server_name: str) -> bool:
        """检查是否有令牌"""
        token = self.load_token(server_name)
        return token is not None and not token.is_expired()


class OAuthFlow:
    """OAuth 认证流程"""

    def __init__(
        self,
        config: OAuthConfig,
        token_store: OAuthTokenStore | None = None,
    ):
        self.config = config
        self.token_store = token_store or OAuthTokenStore()
        self._server: asyncio.Server | None = None
        self._code_exchange_event: asyncio.Event | None = None
        self._authorization_code: str | None = None
        self._error: str | None = None

    async def perform_oauth_flow(self) -> OAuthToken:
        """
        执行完整的 OAuth 认证流程

        Returns:
            OAuthToken: 获取的访问令牌

        Raises:
            OAuthError: 认证失败
        """
        state = secrets.token_urlsafe(32)
        auth_url = self.config.get_authorization_url(state)

        logger.info(f"Opening authorization URL: {auth_url}")
        print(f"请在浏览器中打开以下链接完成授权：\n{auth_url}")

        try:
            webbrowser.open(auth_url)
        except Exception as e:
            logger.warning(f"Failed to open browser: {e}")

        self._code_exchange_event = asyncio.Event()

        self._server = await asyncio.start_server(
            self._handle_callback,
            "localhost",
            8080,
        )

        await self._code_exchange_event.wait()

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        if self._error:
            raise OAuthError(f"OAuth flow failed: {self._error}")

        if not self._authorization_code:
            raise OAuthError("No authorization code received")

        return await self._exchange_code_for_token(self._authorization_code, state)

    async def _handle_callback(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """处理 OAuth 回调"""
        try:
            data = await reader.read(1024)
            request_line = data.decode().split("\r\n")[0]

            if request_line.startswith("GET /callback"):
                query = request_line.split("?", 1)[1] if "?" in request_line else ""
                params = parse_qs(query)

                code = params.get("code", [""])[0]
                error = params.get("error", [""])[0]
                received_state = params.get("state", [""])[0]

                if error:
                    self._error = error
                    self._code_exchange_event.set()
                    response = self._build_error_response(error)
                elif not code:
                    self._error = "No authorization code"
                    self._code_exchange_event.set()
                    response = self._build_error_response("No authorization code")
                else:
                    self._authorization_code = code
                    self._code_exchange_event.set()
                    response = self._build_success_response()

                writer.write(response.encode())
                await writer.drain()

        except Exception as e:
            logger.error(f"Error handling OAuth callback: {e}")
            self._error = str(e)
            if self._code_exchange_event and not self._code_exchange_event.is_set():
                self._code_exchange_event.set()
        finally:
            writer.close()
            await writer.wait_closed()

    def _build_success_response(self) -> str:
        return """HTTP/1.1 200 OK
Content-Type: text/html

<!DOCTYPE html>
<html>
<head><title>OAuth Success</title></head>
<body>
<h1>授权成功！</h1>
<p>你可以关闭此窗口并返回应用程序。</p>
<script>window.close();</script>
</body>
</html>
"""

    def _build_error_response(self, error: str) -> str:
        return f"""HTTP/1.1 400 Bad Request
Content-Type: text/html

<!DOCTYPE html>
<html>
<head><title>OAuth Error</title></head>
<body>
<h1>授权失败</h1>
<p>错误: {error}</p>
<p>请关闭此窗口并重试。</p>
</body>
</html>
"""

    async def _exchange_code_for_token(self, code: str, state: str) -> OAuthToken:
        """用授权码换取访问令牌"""
        import aiohttp

        data = {
            "grant_type": "authorization_code",
            "client_id": self.config.client_id,
            "code": code,
            "redirect_uri": self.config.redirect_uri,
        }

        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.token_url,
                data=urlencode(data),
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise OAuthError(f"Token exchange failed: {resp.status} - {error_text}")

                token_data = await resp.json()
                return OAuthToken.from_dict(token_data)


class OAuthError(Exception):
    """OAuth 错误"""
    pass


class MCPOAuthManager:
    """MCP OAuth 管理器"""

    def __init__(self, token_store: OAuthTokenStore | None = None):
        self.token_store = token_store or OAuthTokenStore()
        self._oauth_configs: dict[str, OAuthConfig] = {}

    def register_server(
        self,
        server_name: str,
        client_id: str,
        authorization_url: str,
        token_url: str,
        client_secret: str | None = None,
        scopes: list[str] | None = None,
    ) -> None:
        """
        注册支持 OAuth 的 MCP 服务器

        Args:
            server_name: 服务器名称
            client_id: OAuth 客户端 ID
            authorization_url: 授权 URL
            token_url: 令牌 URL
            client_secret: 客户端密钥（可选）
            scopes: OAuth 作用域列表
        """
        self._oauth_configs[server_name] = OAuthConfig(
            client_id=client_id,
            client_secret=client_secret,
            authorization_url=authorization_url,
            token_url=token_url,
            scopes=scopes or [],
        )

    def get_auth_header(self, server_name: str) -> str | None:
        """
        获取服务器的认证头

        Args:
            server_name: 服务器名称

        Returns:
            str | None: Authorization 头值，如果无令牌则返回 None
        """
        token = self.token_store.load_token(server_name)
        if token and not token.is_expired():
            return f"{token.token_type} {token.access_token}"
        return None

    async def perform_mcp_oauth_flow(self, server_name: str) -> OAuthToken:
        """
        为 MCP 服务器执行 OAuth 认证流程

        Args:
            server_name: 服务器名称

        Returns:
            OAuthToken: 获取的访问令牌

        Raises:
            OAuthError: 服务器未注册或认证失败
            ValueError: 服务器未注册 OAuth
        """
        if server_name not in self._oauth_configs:
            raise ValueError(f"Server {server_name} is not registered for OAuth")

        config = self._oauth_configs[server_name]
        flow = OAuthFlow(config, self.token_store)

        try:
            token = await flow.perform_oauth_flow()
            self.token_store.save_token(server_name, token)
            logger.info(f"OAuth flow completed for server: {server_name}")
            return token
        except Exception as e:
            logger.error(f"OAuth flow failed for {server_name}: {e}")
            raise OAuthError(f"OAuth flow failed: {e}")

    async def refresh_token_if_needed(self, server_name: str) -> OAuthToken | None:
        """
        如果令牌即将过期，刷新令牌

        Args:
            server_name: 服务器名称

        Returns:
            OAuthToken | None: 刷新后的令牌，如果无需刷新则返回 None
        """
        if server_name not in self._oauth_configs:
            return None

        token = self.token_store.load_token(server_name)
        if not token or not token.refresh_token:
            return None

        import time
        if token.expires_at and token.expires_at - time.time() > 300:
            return None

        config = self._oauth_configs[server_name]
        return await self._refresh_token(server_name, config, token.refresh_token)

    async def _refresh_token(
        self,
        server_name: str,
        config: OAuthConfig,
        refresh_token: str,
    ) -> OAuthToken:
        """刷新访问令牌"""
        import aiohttp

        data = {
            "grant_type": "refresh_token",
            "client_id": config.client_id,
            "refresh_token": refresh_token,
        }

        if config.client_secret:
            data["client_secret"] = config.client_secret

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                config.token_url,
                data=urlencode(data),
                headers=headers,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise OAuthError(f"Token refresh failed: {resp.status} - {error_text}")

                token_data = await resp.json()
                token = OAuthToken.from_dict(token_data)
                self.token_store.save_token(server_name, token)
                logger.info(f"Token refreshed for server: {server_name}")
                return token

    async def revoke_server_tokens(self, server_name: str) -> bool:
        """
        撤销服务器的访问令牌

        Args:
            server_name: 服务器名称

        Returns:
            bool: 是否成功撤销
        """
        if server_name not in self._oauth_configs:
            logger.warning(f"Server {server_name} not registered for OAuth")
            return False

        token = self.token_store.load_token(server_name)
        if not token:
            return True

        config = self._oauth_configs[server_name]

        try:
            await self._revoke_token(config, token.access_token)
        except Exception as e:
            logger.warning(f"Failed to revoke access token: {e}")

        try:
            if token.refresh_token:
                await self._revoke_token(config, token.refresh_token)
        except Exception as e:
            logger.warning(f"Failed to revoke refresh token: {e}")

        self.token_store.delete_token(server_name)
        logger.info(f"Tokens revoked for server: {server_name}")
        return True

    async def _revoke_token(self, config: OAuthConfig, token: str) -> None:
        """撤销令牌"""
        import aiohttp

        data = {
            "token": token,
            "client_id": config.client_id,
        }

        if config.client_secret:
            data["client_secret"] = config.client_secret

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        revoke_url = config.token_url.replace("/token", "/revoke")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    revoke_url,
                    data=urlencode(data),
                    headers=headers,
                ) as resp:
                    if resp.status not in (200, 404):
                        logger.warning(f"Token revocation returned {resp.status}")
        except Exception as e:
            logger.warning(f"Failed to revoke token: {e}")

    def is_authenticated(self, server_name: str) -> bool:
        """
        检查服务器是否已认证

        Args:
            server_name: 服务器名称

        Returns:
            bool: 是否已认证且令牌有效
        """
        if server_name not in self._oauth_configs:
            return False

        token = self.token_store.load_token(server_name)
        return token is not None and not token.is_expired()

    def list_oauth_servers(self) -> list[str]:
        """
        列出已注册 OAuth 的服务器

        Returns:
            List[str]: 服务器名称列表
        """
        return list(self._oauth_configs.keys())


# 全局 OAuth 管理器实例
_oauth_manager: MCPOAuthManager | None = None


def get_oauth_manager() -> MCPOAuthManager:
    """获取全局 OAuth 管理器"""
    global _oauth_manager
    if _oauth_manager is None:
        _oauth_manager = MCPOAuthManager()
    return _oauth_manager
