"""
预批准域名白名单

提供安全检查所需的域名白名单。
"""

PREAPPROVED_HOSTS = {
    # Anthropic
    'platform.claude.com',
    'modelcontextprotocol.io',
    'claude.ai',
    'anthropic.com',
    # 编程语言官方文档
    'docs.python.org',
    'en.cppreference.com',
    'developer.mozilla.org',
    'go.dev',
    'pkg.go.dev',
    'doc.rust-lang.org',
    'www.typescriptlang.org',
    'kotlinlang.org',
    'dart.dev',
    'swift.org',
    'docs.swift.org',
    # 框架
    'react.dev',
    'reactjs.org',
    'nextjs.org',
    'vuejs.org',
    'angular.io',
    'svelte.dev',
    'nodejs.org',
    'expressjs.com',
    'fastapi.tiangolo.com',
    'flask.palletsprojects.com',
    'djangoproject.com',
    'docs.djangoproject.com',
    'rubyonrails.org',
    'sinatrarb.com',
    'spring.io',
    'guides.spring.io',
    # 数据库
    'postgresql.org',
    'docs.postgresql.com',
    'dev.mysql.com',
    'dev.mysql.com',
    'docs.mongodb.com',
    'redis.io',
    'redis-py.readthedocs.io',
    # 开发工具
    'git-scm.com',
    'github.com',
    'gitlab.com',
    'bitbucket.org',
    'docker.com',
    'docs.docker.com',
    'kubernetes.io',
    'kubernetes.io/docs',
    # 包管理器
    'pypi.org',
    'pip.pypa.io',
    'npmjs.com',
    'yarnpkg.com',
    'pnpm.io',
    'cargo.io',
    'crates.io',
    'pub.dev',
    # 云服务
    'aws.amazon.com',
    'docs.aws.amazon.com',
    'cloud.google.com',
    'cloud.google.com/docs',
    'azure.microsoft.com',
    'learn.microsoft.com',
    'digitalocean.com',
    'docs.digitalocean.com',
    # AI/ML
    'openai.com',
    'platform.openai.com',
    'docs.anthropic.com',
    'huggingface.co',
    'huggingface.co/docs',
    'pytorch.org',
    'pytorch.org/docs',
    'tensorflow.org',
    'keras.io',
    # 测试
    'jestjs.io',
    'vitest.dev',
    'pytest.org',
    'unittest.mock.readthedocs.io',
    'rspec.info',
    'junit.org',
    'testng.org',
    # 代码质量
    'ruff.rs',
    'pre-commit.io',
    'eslint.org',
    'typescriptlang.org/docs',
    'black.readthedocs.io',
    'prettier.io',
    # 其他开发相关
    'redis.com',
    'letsencrypt.org',
    'letsencrypt.org/docs',
    'nginx.com',
    'nginx.org/en/docs',
    'apache.org',
    'httpd.apache.org',
    'caddyserver.com',
    'caddyserver.com/docs',
    # 搜索
    'duckduckgo.com',
    'startpage.com',
    # 新闻/博客
    'dev.to',
    'medium.com',
    'stackoverflow.com',
    'stackexchange.com',
    'reddit.com',
    'news.ycombinator.com',
    # 百科
    'wikipedia.org',
    'wikimedia.org',
    # AI 新闻
    'the-decoder.com',
    'venturebeat.com',
    'techcrunch.com',
    # 安全
    'owasp.org',
    'cve.mitre.org',
    'nvd.nist.gov',
}


def is_preapproved_host(host: str) -> bool:
    """
    检查域名是否在白名单中
    
    Args:
        host: 域名（例如 'docs.python.org'）
    
    Returns:
        如果域名在白名单中返回 True
    """
    if not host:
        return False

    host = host.lower()

    if host in PREAPPROVED_HOSTS:
        return True

    for approved in PREAPPROVED_HOSTS:
        if host.endswith(f".{approved}"):
            return True

    return False


def get_preapproved_domains() -> set[str]:
    """获取所有预批准的域名"""
    return PREAPPROVED_HOSTS.copy()


def add_preapproved_domain(domain: str) -> None:
    """
    添加预批准域名（运行时）
    
    注意：这只影响当前进程
    """
    domain = domain.lower()
    PREAPPROVED_HOSTS.add(domain)


def remove_preapproved_domain(domain: str) -> None:
    """
    移除预批准域名（运行时）
    
    注意：这只影响当前进程
    """
    domain = domain.lower()
    PREAPPROVED_HOSTS.discard(domain)
