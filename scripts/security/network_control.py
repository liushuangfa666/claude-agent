"""
网络控制 - Network Control

提供域名和 IP 地址的安全检查，防止恶意网络访问。
"""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass


@dataclass
class NetworkCheckResult:
    """
    网络检查结果

    Attributes:
        allowed: 是否允许
        reason: 原因
        category: 类别 (whitelist/blacklist/private/suspicious)
    """
    allowed: bool
    reason: str
    category: str


# 已知的安全域名白名单
SAFE_DOMAINS: set[str] = {
    # 主流可信服务
    "api.anthropic.com",
    "api.openai.com",
    "api.github.com",
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "pypi.org",
    "pipypi.org",
    "npmjs.org",
    "yarnpkg.com",
    "nuget.org",
    "crates.io",
    "hub.docker.com",
    "docker.io",
    # 国内可信服务
    "passport.baidu.com",
    "login.taobao.com",
    "api.weixin.qq.com",
    # 开发工具
    "pypi.python.org",
    "registry.npmjs.org",
    "repo.maven.apache.org",
    "central.sonatype.org",
}

# 可疑模式 - 匹配这些域名会被拒绝
SUSPICIOUS_PATTERNS: list[re.Pattern] = [
    # 数字过多
    re.compile(r".*\d{5,}"),
    # 常见的恶意模式
    re.compile(r".*(?:login|signin|account|secure|verify)[\w.-]*\.(tk|ml|ga|cf|gq)$"),
    # 短域名后缀
    re.compile(r".*\.(tk|ml|ga|cf|gq|ga)$"),
]

# 私有 IP 范围
PRIVATE_IP_RANGES: list[str] = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "0.0.0.0/8",
]

# 保留 IP 范围
RESERVED_IP_RANGES: list[str] = [
    "224.0.0.0/4",  # Multicast
    "240.0.0.0/4",  # Reserved
    "::1/128",  # IPv6 loopback
    "fc00::/7",  # IPv6 unique local
    "fe80::/10",  # IPv6 link-local
]


class NetworkControl:
    """
    网络访问控制器

    提供域名和 IP 地址的安全检查。

    Attributes:
        allowed_domains: 允许的域名白名单
        blocked_domains: 额外禁止的域名黑名单
        allow_private: 是否允许私有 IP
        allow_reserved: 是否允许保留 IP
        custom_rules: 自定义规则
    """

    def __init__(
        self,
        allowed_domains: set[str] | None = None,
        blocked_domains: set[str] | None = None,
        allow_private: bool = False,
        allow_reserved: bool = False,
    ) -> None:
        """
        初始化网络控制器

        Args:
            allowed_domains: 允许的域名白名单
            blocked_domains: 禁止的域名黑名单
            allow_private: 是否允许私有 IP
            allow_reserved: 是否允许保留 IP
        """
        self.allowed_domains = allowed_domains or set()
        self.blocked_domains = blocked_domains or set()
        self.allow_private = allow_private
        self.allow_reserved = allow_reserved

        # 预编译私有 IP 范围
        self._private_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for net_str in PRIVATE_IP_RANGES:
            try:
                self._private_networks.append(ipaddress.ip_network(net_str))
            except ValueError:
                pass

        # 预编译保留 IP 范围
        self._reserved_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for net_str in RESERVED_IP_RANGES:
            try:
                self._reserved_networks.append(ipaddress.ip_network(net_str))
            except ValueError:
                pass

    def check_domain(self, domain: str) -> tuple[bool, str]:
        """
        检查域名是否允许访问

        Args:
            domain: 域名

        Returns:
            (是否允许, 原因)
        """
        # 清理域名
        domain = domain.lower().strip()
        if not domain:
            return False, "Empty domain"

        # 移除协议前缀
        if "://" in domain:
            domain = domain.split("://", 1)[1]
        # 移除路径
        if "/" in domain:
            domain = domain.split("/", 1)[0]
        # 移除端口
        if ":" in domain:
            domain = domain.split(":", 1)[0]

        # 检查精确匹配的白名单
        if domain in SAFE_DOMAINS:
            return True, "Whitelisted domain"

        # 检查用户指定的白名单
        if domain in self.allowed_domains:
            return True, "User whitelisted domain"

        # 检查黑名单
        if domain in self.blocked_domains:
            return False, "Blocked domain"

        # 检查可疑模式
        for pattern in SUSPICIOUS_PATTERNS:
            if pattern.match(domain):
                return False, f"Domain matches suspicious pattern: {pattern.pattern}"

        # 检查是否为常见 TLD
        common_tlds = {".com", ".org", ".net", ".io", ".co", ".ai", ".dev"}
        for tld in common_tlds:
            if domain.endswith(tld):
                return True, f"Common TLD: {tld}"

        # 检查是否为私有域名（如 localhost）
        if domain in ("localhost", "127.0.0.1", "::1"):
            return False, "Localhost not allowed for external requests"

        # 默认允许（保守策略可以改为拒绝）
        return True, "Default allow"

    def check_ip(self, ip_str: str) -> tuple[bool, str]:
        """
        检查 IP 地址是否允许访问

        Args:
            ip_str: IP 地址字符串

        Returns:
            (是否允许, 原因)
        """
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"Invalid IP address: {ip_str}"

        # 检查私有 IP
        for network in self._private_networks:
            if ip in network:
                if self.allow_private:
                    return True, "Private IP (allowed)"
                return False, "Private IP not allowed"

        # 检查保留 IP
        for network in self._reserved_networks:
            if ip in network:
                if self.allow_reserved:
                    return True, "Reserved IP (allowed)"
                return False, "Reserved IP not allowed"

        # 检查多播地址
        if ip.is_multicast:
            return False, "Multicast address not allowed"

        # 检查未指定地址
        if ip.is_unspecified:
            return False, "Unspecified address not allowed"

        return True, "Public IP allowed"

    def resolve_and_check(self, hostname: str) -> tuple[bool, str]:
        """
        解析域名并检查所有可能的 IP

        Args:
            hostname: 主机名

        Returns:
            (是否允许, 原因)
        """
        # 先检查域名本身
        domain_allowed, domain_reason = self.check_domain(hostname)
        if not domain_allowed:
            return False, domain_reason

        try:
            # 解析域名
            addr_info = socket.getaddrinfo(hostname, None)

            # 检查所有解析出的 IP
            for info in addr_info:
                ip_str = str(info[4][0])
                ip_allowed, ip_reason = self.check_ip(ip_str)
                if not ip_allowed:
                    return False, f"Resolved IP {ip_str}: {ip_reason}"

            return True, f"Resolved to {[info[4][0] for info in addr_info]}"

        except socket.gaierror as e:
            return False, f"DNS resolution failed: {e}"

    def add_whitelist(self, domain: str) -> None:
        """
        添加域名到白名单

        Args:
            domain: 域名
        """
        self.allowed_domains.add(domain.lower())

    def remove_whitelist(self, domain: str) -> None:
        """
        从白名单移除域名

        Args:
            domain: 域名
        """
        self.allowed_domains.discard(domain.lower())

    def add_blacklist(self, domain: str) -> None:
        """
        添加域名到黑名单

        Args:
            domain: 域名
        """
        self.blocked_domains.add(domain.lower())

    def remove_blacklist(self, domain: str) -> None:
        """
        从黑名单移除域名

        Args:
            domain: 域名
        """
        self.blocked_domains.discard(domain.lower())


# 全局网络控制器实例
_default_controller: NetworkControl | None = None


def get_network_control() -> NetworkControl:
    """
    获取全局网络控制器实例

    Returns:
        NetworkControl 实例
    """
    global _default_controller
    if _default_controller is None:
        _default_controller = NetworkControl()
    return _default_controller


def check_domain(domain: str) -> tuple[bool, str]:
    """
    便捷函数：检查域名

    Args:
        domain: 域名

    Returns:
        (是否允许, 原因)
    """
    return get_network_control().check_domain(domain)


def check_ip(ip_str: str) -> tuple[bool, str]:
    """
    便捷函数：检查 IP

    Args:
        ip_str: IP 地址

    Returns:
        (是否允许, 原因)
    """
    return get_network_control().check_ip(ip_str)


if __name__ == "__main__":
    # 简单测试
    control = NetworkControl()

    # 测试域名检查
    test_domains = [
        "api.github.com",
        "api.anthropic.com",
        "localhost",
        "evil.tk",
        "suspicious.ml",
        "example.com",
        "12345.xyz",
    ]

    print("Domain checks:")
    for domain in test_domains:
        allowed, reason = control.check_domain(domain)
        print(f"  {domain}: {'ALLOW' if allowed else 'DENY'} - {reason}")

    print("\nIP checks:")
    test_ips = ["8.8.8.8", "192.168.1.1", "10.0.0.1", "127.0.0.1", "224.0.0.1"]
    for ip_str in test_ips:
        allowed, reason = control.check_ip(ip_str)
        print(f"  {ip_str}: {'ALLOW' if allowed else 'DENY'} - {reason}")

    print("\nResolve checks:")
    resolve_tests = ["api.github.com", "google.com"]
    for host in resolve_tests:
        allowed, reason = control.resolve_and_check(host)
        print(f"  {host}: {'ALLOW' if allowed else 'DENY'} - {reason}")
