#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Integration tests for Flask-Redis."""

import flask
import pytest
from unittest import mock

from flask_redis import FlaskRedis  # Adjust the import based on your package structure


@pytest.fixture
def app():
    return flask.Flask(__name__)


def test_constructor(app):
    """Test that a constructor with app instance initializes the connection."""
    redis_client = FlaskRedis(app)
    assert redis_client._redis_client is not None
    assert hasattr(redis_client._redis_client, "connection_pool")


def test_init_app(app):
    """Test that a constructor without app instance does not initialize the connection.

    After FlaskRedis.init_app(app) is called, the connection is initialized."""
    redis_client = FlaskRedis()
    assert redis_client._redis_client is None
    redis_client.init_app(app)
    assert redis_client._redis_client is not None
    assert hasattr(redis_client._redis_client, "connection_pool")
    if hasattr(app, "extensions"):
        assert "redis" in app.extensions
        assert app.extensions["redis"] == redis_client


def test_custom_prefix(app):
    """Test that config prefixes enable distinct connections."""
    app.config["DBA_URL"] = "redis://localhost:6379/1"
    app.config["DBB_URL"] = "redis://localhost:6379/2"
    redis_a = FlaskRedis(app, config_prefix="DBA")
    redis_b = FlaskRedis(app, config_prefix="DBB")
    assert redis_a._redis_client.connection_pool.connection_kwargs["db"] == 1
    assert redis_b._redis_client.connection_pool.connection_kwargs["db"] == 2


@pytest.mark.parametrize(
    ["strict_flag", "allowed_names"],
    [
        [True, {"Redis", "StrictRedis"}],
        [False, {"Redis"}],
    ],
)
def test_strict_parameter(app, strict_flag, allowed_names):
    """Test that initializing with the strict parameter uses the correct client class."""
    redis_client = FlaskRedis(app, strict=strict_flag)
    assert redis_client._redis_client is not None
    assert type(redis_client._redis_client).__name__ in allowed_names


def test_sentinel_connection(app, mocker):
    """Test that FlaskRedis can connect to Redis Sentinel."""
    app.config["REDIS_URL"] = "redis+sentinel://localhost:26379/mymaster/0"

    # Mock Sentinel to prevent actual network calls
    mock_sentinel = mocker.patch("flask_redis.Sentinel", autospec=True)
    mock_sentinel_instance = mock_sentinel.return_value
    mock_master_for = mock_sentinel_instance.master_for
    mock_master_for.return_value = mock.MagicMock()

    redis_client = FlaskRedis(app)

    # Verify that Sentinel was initialized with the correct parameters
    mock_sentinel.assert_called_once()
    mock_master_for.assert_called_once_with(
        "mymaster",
        db=0,
        socket_timeout=None,
        decode_responses=True,
        ssl_params={},
        auth_params={},
    )
    assert redis_client._redis_client is not None


def test_ssl_connection(app):
    """Test that FlaskRedis can connect with SSL parameters."""
    app.config["REDIS_URL"] = "rediss://localhost:6379/0"
    redis_client = FlaskRedis(app)
    assert redis_client._redis_client is not None
    assert redis_client._redis_client.connection_pool.connection_kwargs.get("ssl") is True


def test_ssl_sentinel_connection(app, mocker):
    """Test that FlaskRedis can connect to Redis Sentinel with SSL."""
    app.config[
        "REDIS_URL"
    ] = "rediss+sentinel://localhost:26379/mymaster/0?ssl_cert_reqs=required"

    # Mock Sentinel to prevent actual network calls
    mock_sentinel = mocker.patch("flask_redis.Sentinel", autospec=True)
    mock_sentinel_instance = mock_sentinel.return_value
    mock_master_for = mock_sentinel_instance.master_for
    mock_master_for.return_value = mock.MagicMock()

    redis_client = FlaskRedis(app)

    # Verify that Sentinel was initialized with SSL parameters
    expected_ssl_params = {"ssl": True, "ssl_cert_reqs": ssl.CERT_REQUIRED}
    mock_sentinel.assert_called_once()
    mock_master_for.assert_called_once_with(
        "mymaster",
        db=0,
        socket_timeout=None,
        decode_responses=True,
        ssl_params=expected_ssl_params,
        auth_params={},
    )
    assert redis_client._redis_client is not None

