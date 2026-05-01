#!/usr/bin/env python3
"""CDK app entry — provisions IoT Things in iotea-workloads-spikes-sitewise.

Run from inside ``infra/cdk/``::

    aws sso login --profile spikes-sitewise
    export AWS_PROFILE=spikes-sitewise
    cdk synth
    cdk deploy

See ``docs/SBCC-INFRA-0001-iot-hello-world-cdk.md`` for the full operator
runbook (SSO login, bootstrap, deploy, fetch-credentials, mqtt-test,
decommission-thing).
"""

from __future__ import annotations

import sys

from pathlib import Path

import aws_cdk as cdk

# Make ``stacks/`` importable when ``cdk synth`` runs from infra/cdk/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stacks.iot_hello_stack import IotHelloStack

DEFAULT_REGION = "us-west-2"
DEFAULT_THING = "hw-pi-001"
DEFAULT_POLICY_NAME = "iot-hello-world"


def _resolve_thing_names(app: cdk.App) -> list[str]:
    """Read ``thingNames`` from CDK context (list[str] or single str)."""
    raw = app.node.try_get_context("thingNames")
    if raw is None:
        single = app.node.try_get_context("thingName")
        return [single] if single else [DEFAULT_THING]
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list) and all(isinstance(name, str) for name in raw):
        return list(raw)
    msg = (
        "context value `thingNames` must be str or list[str]; "
        "see infra/cdk/cdk.context.example.json"
    )
    raise TypeError(msg)


def _resolve_env(app: cdk.App) -> cdk.Environment:
    """Pin region; account flows from CDK_DEFAULT_ACCOUNT (CLI profile)."""
    region = app.node.try_get_context("region") or DEFAULT_REGION
    return cdk.Environment(region=region)


app = cdk.App()
thing_names = _resolve_thing_names(app)
policy_name = app.node.try_get_context("policyName") or DEFAULT_POLICY_NAME
env = _resolve_env(app)

IotHelloStack(
    app,
    "IotHelloStack",
    env=env,
    thing_names=thing_names,
    policy_name=policy_name,
)

app.synth()
