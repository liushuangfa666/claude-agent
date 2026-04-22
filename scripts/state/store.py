"""
状态存储核心实现

基于发布-订阅模式的泛型状态存储。
使用 Object.is() 语义避免无意义更新。
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Callable, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
S = TypeVar("S")

ListenerId = int


def object_is(x, y) -> bool:
    """
    Object.is 语义比较

    - 如果 x is y 返回 True
    - 如果都是 None 返回 False
    - 如果都是 NaN 返回 True
    - 其他情况返回 x == y
    """
    if x is y:
        return True
    if x is None or y is None:
        return False
    if isinstance(x, float) and isinstance(y, float):
        return x != x and y != y  # NaN check
    return x == y


class Store(Generic[T]):
    """
    简单发布-订阅状态存储

    特性：
    - 基于 Object.is() 避免无意义更新
    - 可选 onChange 钩子用于副作用
    - subscribe 返回取消订阅函数
    - subscribe_selector 支持基于选择器的订阅

    Example:
        store = Store(initial_state)

        # 基础订阅
        unsubscribe = store.subscribe(lambda prev, next: print("changed!"))
        store.set_state(lambda s: {"count": s["count"] + 1})
        unsubscribe()

        # 选择器订阅
        store.subscribe_selector(
            lambda s: s.items_count,
            lambda prev, next: print(f"items: {prev} -> {next}")
        )
    """

    def __init__(
        self,
        initial_state: T,
        on_change: Callable[[T, T], None] | None = None,
    ) -> None:
        """
        初始化状态存储

        Args:
            initial_state: 初始状态
            on_change: 可选的全局变更回调
        """
        self._state: T = deepcopy(initial_state)
        self._on_change = on_change
        self._listeners: dict[ListenerId, Callable[[T, T], None]] = {}
        self._next_listener_id: ListenerId = 0

    def get_state(self) -> T:
        """获取当前状态的深拷贝"""
        return deepcopy(self._state)

    def set_state(self, updater: Callable[[T], T]) -> None:
        """
        更新状态

        Args:
            updater: 接收当前状态，返回新状态的函数
        """
        prev = deepcopy(self._state)
        next_state = updater(self._state)

        if object_is(prev, next_state):
            return

        self._state = deepcopy(next_state)

        if self._on_change:
            try:
                self._on_change(prev, self._state)
            except Exception as e:
                logger.error(f"Error in on_change callback: {e}")

        for listener in list(self._listeners.values()):
            try:
                listener(prev, self._state)
            except Exception as e:
                logger.error(f"Error in listener: {e}")

    def subscribe(self, listener: Callable[[T, T], None]) -> Callable[[], None]:
        """
        订阅状态变更

        Args:
            listener: 状态变更回调，签名为 (prev: T, next: T) -> None

        Returns:
            取消订阅函数
        """
        listener_id = self._next_listener_id
        self._next_listener_id += 1
        self._listeners[listener_id] = listener

        def unsubscribe() -> None:
            del self._listeners[listener_id]

        return unsubscribe

    def subscribe_selector(
        self,
        selector: Callable[[T], S],
        listener: Callable[[S, S], None],
    ) -> Callable[[], None]:
        """
        基于选择器的订阅

        只在选择结果变化时触发回调。

        Args:
            selector: 选择器函数，从状态中提取部分数据
            listener: 变更回调，签名为 (prev: S, next: S) -> None

        Returns:
            取消订阅函数
        """
        current = selector(self._state)

        def wrapper(prev: T, next: T) -> None:
            prev_selected = selector(prev)
            next_selected = selector(next)
            if prev_selected != next_selected:
                try:
                    listener(prev_selected, next_selected)
                except Exception as e:
                    logger.error(f"Error in selector listener: {e}")

        return self.subscribe(wrapper)


def create_app_store(session_id: str) -> Store:
    """创建 AppState Store 的便捷函数"""
    from .app_state import create_default_app_state

    initial = create_default_app_state(session_id)
    return Store(initial)
