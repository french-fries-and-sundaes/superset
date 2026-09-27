# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from typing import Any

import pytest

from superset.constants import PASSWORD_MASK
from superset.databases.ssh_tunnel.models import SSHTunnel
from superset.utils.ssh_tunnel import (
    get_default_port,
    mask_password_info,
    unmask_password_info,
)

SECRET_KEYS = ("password", "private_key", "private_key_password")


@pytest.mark.parametrize("key", SECRET_KEYS)
def test_mask_password_info_masks_present_key(key: str) -> None:
    ssh_tunnel: dict[str, Any] = {
        "server_address": "ssh.example.com",
        "server_port": 22,
        "username": "user",
        key: "super-secret",
    }
    result = mask_password_info(ssh_tunnel)
    assert result is ssh_tunnel
    assert result[key] == PASSWORD_MASK
    assert result["server_address"] == "ssh.example.com"
    assert result["server_port"] == 22
    assert result["username"] == "user"


def test_mask_password_info_masks_all_keys() -> None:
    ssh_tunnel: dict[str, Any] = {
        "password": "pw",
        "private_key": "-----BEGIN KEY-----",
        "private_key_password": "pk-pw",
    }
    result = mask_password_info(ssh_tunnel)
    assert result == {key: PASSWORD_MASK for key in SECRET_KEYS}
    assert "pw" not in result.values()
    assert "-----BEGIN KEY-----" not in result.values()


def test_mask_password_info_does_not_add_absent_keys() -> None:
    ssh_tunnel: dict[str, Any] = {"server_address": "ssh.example.com"}
    result = mask_password_info(ssh_tunnel)
    assert result == {"server_address": "ssh.example.com"}
    for key in SECRET_KEYS:
        assert key not in result


@pytest.mark.parametrize("key", SECRET_KEYS)
def test_mask_password_info_removes_none_keys(key: str) -> None:
    ssh_tunnel: dict[str, Any] = {"server_address": "ssh.example.com", key: None}
    result = mask_password_info(ssh_tunnel)
    assert key not in result
    assert result == {"server_address": "ssh.example.com"}


def test_mask_password_info_empty_string_is_masked() -> None:
    ssh_tunnel: dict[str, Any] = {"password": ""}
    assert mask_password_info(ssh_tunnel) == {"password": PASSWORD_MASK}


def _model() -> SSHTunnel:
    return SSHTunnel(
        password="stored-pw",  # noqa: S106
        private_key="stored-key",
        private_key_password="stored-pk-pw",  # noqa: S106
    )


@pytest.mark.parametrize("key", SECRET_KEYS)
def test_unmask_password_info_restores_masked_value(key: str) -> None:
    model = _model()
    ssh_tunnel: dict[str, Any] = {"username": "user", key: PASSWORD_MASK}
    result = unmask_password_info(ssh_tunnel, model)
    assert result is ssh_tunnel
    assert result[key] == getattr(model, key)
    assert result["username"] == "user"


def test_unmask_password_info_restores_all_masked_values() -> None:
    model = _model()
    ssh_tunnel: dict[str, Any] = {key: PASSWORD_MASK for key in SECRET_KEYS}
    result = unmask_password_info(ssh_tunnel, model)
    assert result == {
        "password": "stored-pw",
        "private_key": "stored-key",
        "private_key_password": "stored-pk-pw",
    }


@pytest.mark.parametrize("key", SECRET_KEYS)
def test_unmask_password_info_keeps_new_value(key: str) -> None:
    ssh_tunnel: dict[str, Any] = {key: "brand-new-secret"}
    result = unmask_password_info(ssh_tunnel, _model())
    assert result == {key: "brand-new-secret"}


def test_unmask_password_info_does_not_add_absent_keys() -> None:
    ssh_tunnel: dict[str, Any] = {"username": "user"}
    result = unmask_password_info(ssh_tunnel, _model())
    assert result == {"username": "user"}


def test_unmask_password_info_keeps_none_and_empty_values() -> None:
    ssh_tunnel: dict[str, Any] = {"password": None, "private_key": ""}
    result = unmask_password_info(ssh_tunnel, _model())
    assert result == {"password": None, "private_key": ""}


def test_unmask_password_info_mixed_values() -> None:
    ssh_tunnel: dict[str, Any] = {
        "password": PASSWORD_MASK,
        "private_key": "new-key",
    }
    result = unmask_password_info(ssh_tunnel, _model())
    assert result == {"password": "stored-pw", "private_key": "new-key"}


@pytest.mark.parametrize(
    "backend,expected",
    [
        ("postgresql", 5432),
        ("mysql", 3306),
        ("oracle", 1521),
        ("mssql", 1433),
    ],
)
def test_get_default_port_known_backend(backend: str, expected: int) -> None:
    assert get_default_port(backend) == expected


@pytest.mark.parametrize("backend", ["sqlite", "trino", "", "PostgreSQL"])
def test_get_default_port_unknown_backend(backend: str) -> None:
    assert get_default_port(backend) is None
