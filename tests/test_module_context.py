import pytest

from utils.module_context import (
    clear_active_module_id,
    get_active_module_id,
    set_active_module_id,
)


MODULES = [{"module_id": 1}, {"module_id": 2}]


def test_active_module_is_scoped_by_user_and_survives_reruns():
    state = {}
    set_active_module_id(state, "alice", 2, MODULES)

    assert get_active_module_id(state, "alice", MODULES) == 2
    assert get_active_module_id(state, "bob", MODULES) == 1


def test_invalid_or_deleted_module_falls_back_to_a_valid_owned_module():
    state = {}
    set_active_module_id(state, "alice", 2, MODULES)

    assert get_active_module_id(state, "alice", [{"module_id": 1}]) == 1


def test_setting_module_rejects_modules_not_owned_by_user():
    with pytest.raises(ValueError):
        set_active_module_id({}, "alice", 99, MODULES)


def test_clear_active_module_removes_only_that_users_context():
    state = {}
    set_active_module_id(state, "alice", 2, MODULES)
    set_active_module_id(state, "bob", 2, MODULES)

    clear_active_module_id(state, "alice")

    assert get_active_module_id(state, "alice", MODULES) == 1
    assert get_active_module_id(state, "bob", MODULES) == 2
