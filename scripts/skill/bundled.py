"""
内置技能

提供内置的默认技能。
"""

from .skill import LoadedSkill, SkillConfig


def get_bundled_skills() -> list[SkillConfig]:
    """获取所有内置技能"""
    return [
        _get_verify_skill(),
        _get_pr_review_skill(),
        _get_refactor_skill(),
        _get_debug_skill(),
        _get_test_skill(),
        _get_docs_skill(),
    ]


def _get_verify_skill() -> SkillConfig:
    """验证技能"""
    return SkillConfig(
        name="verify",
        description="Verify implementation against specification",
        when_to_use="When you need to verify that code matches requirements",
        argument_hint="<verification target>",
        arguments=[{"name": "target", "description": "What to verify"}],
        allowed_tools=["Read", "Bash", "Glob"],
        context="fork",
        agent="general-purpose",
        effort="medium",
        paths=["**/*.py", "**/*.js", "**/*.ts"],
        content="""You are a verification specialist.

Your task is to verify that the implementation matches the specification.

## Verification Target
$ARGUMENTS

## Verification Steps
1. Read the relevant source files
2. Compare implementation against requirements
3. Run any available tests
4. Report discrepancies

## Output Format
Report verification results including:
- What matches
- What doesn't match
- Missing functionality
- Test results
""",
    )


def _get_pr_review_skill() -> SkillConfig:
    """PR 审查技能"""
    return SkillConfig(
        name="pr-review",
        description="Review pull request changes",
        when_to_use="When you need to review a PR",
        argument_hint="<pr-url>",
        arguments=[{"name": "pr_url", "description": "PR URL"}],
        allowed_tools=["Read", "Bash", "WebFetch"],
        context="fork",
        agent="general-purpose",
        effort="medium",
        content="""You are a code reviewer.

Your task is to review pull request changes for quality, security, and best practices.

## PR to Review
$ARGUMENTS

## Review Focus
1. Code quality and style
2. Security concerns
3. Performance implications
4. Test coverage
5. Documentation updates

## Output Format
Provide a structured review including:
- Summary of changes
- Issues found (with severity)
- Suggestions for improvement
- Approval recommendation
""",
    )


def _get_refactor_skill() -> SkillConfig:
    """重构技能"""
    return SkillConfig(
        name="refactor",
        description="Refactor code while preserving behavior",
        when_to_use="When you need to improve code structure",
        argument_hint="<target>",
        arguments=[{"name": "target", "description": "Code to refactor"}],
        allowed_tools=["Read", "Edit", "Bash"],
        context="fork",
        agent="general-purpose",
        effort="high",
        paths=["**/*.py"],
        content="""You are a refactoring specialist.

Your task is to improve code structure while preserving behavior.

## Refactoring Target
$ARGUMENTS

## Principles
1. Preserve all existing functionality
2. Improve code readability
3. Reduce duplication
4. Improve maintainability
5. Add/update tests

## Process
1. Understand the current code
2. Identify improvement opportunities
3. Plan refactoring steps
4. Execute changes
5. Verify tests still pass
""",
    )


def _get_debug_skill() -> SkillConfig:
    """调试技能"""
    return SkillConfig(
        name="debug",
        description="Debug issues in the codebase",
        when_to_use="When you need to find and fix bugs",
        argument_hint="<issue description>",
        arguments=[{"name": "issue", "description": "Issue to debug"}],
        allowed_tools=["Read", "Grep", "Bash"],
        context="fork",
        agent="general-purpose",
        effort="medium",
        content="""You are a debugging specialist.

Your task is to identify and fix issues in the codebase.

## Issue to Debug
$ARGUMENTS

## Debugging Process
1. Reproduce the issue
2. Identify root cause
3. Locate relevant code
4. Implement fix
5. Verify fix works

## Output Format
- Issue description
- Root cause analysis
- Fix implementation
- Verification steps
""",
    )


def _get_test_skill() -> SkillConfig:
    """测试技能"""
    return SkillConfig(
        name="test",
        description="Write and run tests",
        when_to_use="When you need to add or update tests",
        argument_hint="<target>",
        arguments=[{"name": "target", "description": "What to test"}],
        allowed_tools=["Read", "Write", "Bash"],
        context="fork",
        agent="general-purpose",
        effort="medium",
        paths=["**/test_*.py", "**/*_test.py"],
        content="""You are a testing specialist.

Your task is to write and run tests.

## Test Target
$ARGUMENTS

## Testing Requirements
1. Cover normal cases
2. Cover edge cases
3. Cover error cases
4. Use appropriate assertions
5. Follow project test patterns

## Process
1. Understand the code to test
2. Identify test cases
3. Write tests
4. Run tests to verify
""",
    )


def _get_docs_skill() -> SkillConfig:
    """文档技能"""
    return SkillConfig(
        name="docs",
        description="Generate or update documentation",
        when_to_use="When you need to create or update docs",
        argument_hint="<target>",
        arguments=[{"name": "target", "description": "What to document"}],
        allowed_tools=["Read", "Write", "Glob"],
        context="fork",
        agent="general-purpose",
        effort="low",
        paths=["**/*.md", "**/docs/**"],
        content="""You are a documentation specialist.

Your task is to create or update documentation.

## Documentation Target
$ARGUMENTS

## Documentation Guidelines
1. Use clear, concise language
2. Include code examples where appropriate
3. Follow existing documentation style
4. Keep docs up to date

## Process
1. Review existing documentation
2. Identify what needs to be added/updated
3. Write documentation
4. Verify formatting
""",
    )


def register_bundled_skills(loader) -> None:
    """注册内置技能到加载器"""
    for config in get_bundled_skills():
        loaded = LoadedSkill(config=config)
        loader._loaded_skills[config.name] = loaded
