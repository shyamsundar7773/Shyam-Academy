from collections.abc import Mapping, MutableMapping, Sequence


_ACTIVE_MODULES_KEY = "active_module_ids_by_user"


def get_active_module_id(
    state: MutableMapping,
    user_id: str,
    modules: Sequence[Mapping],
) -> int | None:
    module_ids = {int(module["module_id"]) for module in modules}
    stored = state.get(_ACTIVE_MODULES_KEY, {}).get(user_id)
    if stored in module_ids:
        return int(stored)
    return int(modules[0]["module_id"]) if modules else None


def set_active_module_id(
    state: MutableMapping,
    user_id: str,
    module_id: int,
    modules: Sequence[Mapping],
) -> int:
    module_ids = {int(module["module_id"]) for module in modules}
    if module_id not in module_ids:
        raise ValueError("The selected module could not be found.")
    active = dict(state.get(_ACTIVE_MODULES_KEY, {}))
    active[user_id] = int(module_id)
    state[_ACTIVE_MODULES_KEY] = active
    state["active_module_id"] = int(module_id)
    return int(module_id)


def clear_active_module_id(state: MutableMapping, user_id: str) -> None:
    active = dict(state.get(_ACTIVE_MODULES_KEY, {}))
    active.pop(user_id, None)
    state[_ACTIVE_MODULES_KEY] = active
    state.pop("active_module_id", None)
