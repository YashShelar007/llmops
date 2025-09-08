# backend/app/__init__.py
from __future__ import annotations
import os
from functools import lru_cache

try:
    import boto3
    _ssm = boto3.client("ssm")
except Exception:  # local dev without AWS SDK is fine
    _ssm = None

@lru_cache(maxsize=None)
def ssm_get(name: str, decrypt: bool = True) -> str | None:
    """Return SSM parameter value or None if unavailable."""
    if not name or _ssm is None:
        return None
    try:
        resp = _ssm.get_parameter(Name=name, WithDecryption=decrypt)
        return resp.get("Parameter", {}).get("Value")
    except Exception:
        return None

def ensure_env_from_ssm(env_key: str, ssm_name_env_key: str, decrypt: bool = True):
    """
    If ENV[env_key] is missing, and ENV[ssm_name_env_key] is set to an SSM path,
    fetch and set ENV[env_key].
    """
    if os.getenv(env_key):
        return
    ssm_name = os.getenv(ssm_name_env_key)
    if not ssm_name:
        return
    val = ssm_get(ssm_name, decrypt=decrypt)
    if val:
        os.environ[env_key] = val
