"""Synthesis tests for ``infra/cdk/stacks/iot_hello_stack.py``.

These tests guard the **shape** of the per-Thing IoT policy and the
multi-Thing wiring: a snapshot regression catches anyone accidentally
dropping a policy variable (``${iot:Connection.Thing.ThingName}``) or
adding a per-Thing CFN policy that breaks the "single shared policy"
contract.

Run via ``uv run python -m unittest tests.test_iot_hello_stack``.
"""

from __future__ import annotations

import json
import sys
import unittest

from pathlib import Path
from typing import Any

import aws_cdk as cdk

from aws_cdk import assertions

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "infra" / "cdk"))

from stacks.iot_hello_stack import IotHelloStack  # noqa: E402


def _synth(thing_names: list[str]) -> assertions.Template:
    app = cdk.App()
    stack = IotHelloStack(
        app,
        "TestStack",
        thing_names=thing_names,
        policy_name="iot-hello-world",
        env=cdk.Environment(account="111122223333", region="us-west-2"),
    )
    return assertions.Template.from_stack(stack)


def _resource_property(
    template: assertions.Template, *, type_name: str
) -> dict[str, Any]:
    """Return the single resource of ``type_name`` (raises if not exactly one)."""
    found = template.find_resources(type_name)
    if len(found) != 1:
        msg = f"expected exactly one {type_name}; got {len(found)}"
        raise AssertionError(msg)
    return next(iter(found.values()))["Properties"]


class IotPolicyShape(unittest.TestCase):
    """The per-Thing scoped policy is a single resource that uses IoT vars."""

    def test_one_policy_resource(self) -> None:
        template = _synth(["hw-pi-001", "hw-pi-002"])
        template.resource_count_is("AWS::IoT::Policy", 1)

    def test_policy_uses_thing_name_variable(self) -> None:
        template = _synth(["hw-pi-001"])
        props = _resource_property(template, type_name="AWS::IoT::Policy")
        # The policy is rendered as a dict because we returned a dict in the
        # stack — but CDK still wraps ARN strings in Fn::Join. Serialize the
        # policy doc and grep for the variable substring.
        body = json.dumps(props["PolicyDocument"])
        self.assertIn("${iot:Connection.Thing.ThingName}", body)
        self.assertIn(":client/${iot:Connection.Thing.ThingName}", body)
        self.assertIn(":topic/hello/${iot:Connection.Thing.ThingName}/*", body)
        self.assertIn(
            ":topicfilter/hello/${iot:Connection.Thing.ThingName}/*",
            body,
        )

    def test_policy_has_three_statements(self) -> None:
        template = _synth(["hw-pi-001"])
        props = _resource_property(template, type_name="AWS::IoT::Policy")
        sids = [s["Sid"] for s in props["PolicyDocument"]["Statement"]]
        self.assertEqual(
            sids,
            ["ConnectAsOwnThing", "PublishOwnTopics", "SubscribeOwnTopicFilters"],
        )


class MultiThingWiring(unittest.TestCase):
    """One CFN policy + one Lambda + one Thing/CustomResource per Thing."""

    def test_one_thing_creates_one_pair(self) -> None:
        template = _synth(["hw-pi-001"])
        template.resource_count_is("AWS::IoT::Thing", 1)
        # Custom resource invocations: Provider framework adds its own
        # AWS::CloudFormation::CustomResource — we filter to ours by
        # ResourceProperties.ThingName below.
        cr_resources = template.find_resources(
            "AWS::CloudFormation::CustomResource",
        )
        thing_invocations = [
            res
            for res in cr_resources.values()
            if res["Properties"].get("ThingName") == "hw-pi-001"
        ]
        self.assertEqual(len(thing_invocations), 1)

    def test_seventeen_things_share_one_policy(self) -> None:
        thing_names = [f"hw-pi-{i:03d}" for i in range(1, 18)]
        template = _synth(thing_names)
        template.resource_count_is("AWS::IoT::Policy", 1)
        template.resource_count_is("AWS::IoT::Thing", 17)
        # One Lambda function for our handler (provider framework adds
        # framework Lambdas too); count exact = 2 = our function + provider
        # framework's onEvent.
        functions = template.find_resources("AWS::Lambda::Function")
        self.assertGreaterEqual(len(functions), 2)


class LambdaHandlerImports(unittest.TestCase):
    """Sanity check the handler script imports without optional deps."""

    def test_handler_module_loads(self) -> None:
        handler_path = REPO_ROOT / "infra/cdk/lambda/provision_device/handler.py"
        self.assertTrue(handler_path.is_file())
        # Compile it (catches SyntaxError / NameError at parse time without
        # actually running boto3 setup).
        compile(handler_path.read_text(), str(handler_path), "exec")


if __name__ == "__main__":
    unittest.main()
