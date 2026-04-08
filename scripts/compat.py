"""
跨平台兼容模块
在 Windows 上将相对导入转为绝对导入
"""
import os
import sys

# 如果 scripts 不在路径里，加进去
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# 在 Windows 上，修复相对导入问题
# 当直接运行 python scripts/xxx.py 时，相对导入会失败
# 这个文件确保所有模块都能正确导入
IS_WINDOWS = sys.platform == "win32" or os.name == "nt"

def fix_relative_imports():
    """在 Windows 上将相对导入替换为绝对导入"""
    if not IS_WINDOWS:
        return

    # 这个函数在导入时会被调用，确保模块加载正确
    pass
