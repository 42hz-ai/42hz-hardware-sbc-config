"""Thin boto3 session/client helpers for IoT + Secrets Manager.

Importable from both the CLI and the CDK custom-resource Lambda. The Lambda
runtime auto-injects credentials, so callers there pass ``profile=None`` (the
default) and rely on the AWS execution role; the CLI honours ``AWS_PROFILE``
or the explicit ``profile`` argument.
"""

from __future__ import annotations

from typing import Any

import boto3

from boto3 import Session

DEFAULT_REGION = "us-west-2"


def build_session(
    *,
    profile: str | None = None,
    region: str | None = None,
) -> Session:
    """Build a boto3 Session, defaulting region to ``us-west-2``.

    ``profile=None`` lets boto3 fall back to ``AWS_PROFILE`` / instance role
    (Lambda) so the same code path works for both callers.
    """
    return boto3.Session(
        profile_name=profile,
        region_name=region or DEFAULT_REGION,
    )


def iot_client(
    *,
    session: Session | None = None,
    profile: str | None = None,
    region: str | None = None,
) -> Any:
    """Return a boto3 ``iot`` client (data-plane control APIs)."""
    sess = session or build_session(profile=profile, region=region)
    return sess.client("iot")


def secrets_client(
    *,
    session: Session | None = None,
    profile: str | None = None,
    region: str | None = None,
) -> Any:
    """Return a boto3 ``secretsmanager`` client."""
    sess = session or build_session(profile=profile, region=region)
    return sess.client("secretsmanager")
