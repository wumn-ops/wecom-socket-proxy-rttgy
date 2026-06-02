"""需求登记「所属模块」选项解析（按所属系统后缀 _MES / _VPS / _CPS 过滤）。"""

from __future__ import annotations


def parse_module_list(raw: str) -> list[str]:
    modules: list[str] = []
    for part in raw.split(","):
        text = part.strip()
        if text:
            modules.append(text)
    return modules


def module_belongs_to_system(module: str, system: str) -> bool:
    system = system.strip()
    module = module.strip()
    if not system or not module:
        return False
    return module.endswith(f"_{system}")


def modules_for_system(modules: list[str], system: str) -> list[str]:
    return [item for item in modules if module_belongs_to_system(item, system)]


def build_modules_by_system(
    modules: list[str],
    systems: list[str],
) -> dict[str, list[str]]:
    return {system: modules_for_system(modules, system) for system in systems}
