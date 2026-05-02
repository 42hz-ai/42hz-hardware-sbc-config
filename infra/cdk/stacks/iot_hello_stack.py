"""IoT hello-world stack — Thing(s), per-Thing-scoped policy, custom-resource Lambda.

Resources (per stack):

* **One** ``AWS::IoT::Policy`` (``CfnPolicy``). Uses IoT policy variables so it
  scales to N Things without per-Thing CFN policies. See
  ``docs/SBCC-INFRA-0001-iot-hello-world-cdk.md`` § *IoT policy*.
* **Greengrass TES (default)** — ``AWS::IAM::Role`` trusted by
  ``credentials.iot.amazonaws.com`` plus ``AWS::IoT::RoleAlias``; device policy
  includes ``iot:AssumeRoleWithCertificate``. Opt out with context
  ``createGreengrassTokenExchangeRole: false``.
* **One** Lambda + ``Provider`` (custom-resource framework). The handler imports
  ``sbc_config.modules.iot.lifecycle`` so the CLI's ``decommission-thing`` and
  the CFN ``Delete`` event share one teardown sequence.

Per Thing (looped from CDK context ``thingNames``):

* ``AWS::IoT::Thing`` (``CfnThing``).
* ``AWS::CloudFormation::CustomResource`` that invokes the Lambda for
  ``Create`` / ``Update`` / ``Delete`` against the per-Thing certificate +
  ``AWS::SecretsManager::Secret`` lifecycle.

The Secret is created **inside the Lambda** (no ``CfnSecret`` here) so the
private key never lives in synthesized CloudFormation outputs.
"""

from __future__ import annotations

import shutil
import sys
import tempfile

from pathlib import Path
from typing import Any

import aws_cdk as cdk

from aws_cdk import (
    CfnOutput,
    CustomResource,
    Duration,
    RemovalPolicy,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_iot as iot,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    custom_resources as cr,
)
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from sbc_config.modules.iot.defaults import (  # noqa: E402
    DEFAULT_GREENGRASS_TES_ROLE_ALIAS,
)

HANDLER_PATH = REPO_ROOT / "infra/cdk/lambda/provision_device/handler.py"

# AWS IoT rejects policy documents over this character count. Do not enumerate
# per-Thing ARNs for Greengrass MQTT (grows with ``thingNames``); use
# ``${iot:Connection.Thing.ThingName}`` in those paths instead.
IOT_POLICY_DOCUMENT_MAX_CHARS = 2048

_THING_NAME_VAR = "${iot:Connection.Thing.ThingName}"


def _stage_lambda_asset() -> Path:
    """Copy ``handler.py`` + the ``sbc_config.modules.iot`` subtree to a temp dir.

    Why staging instead of CDK ``BundlingOptions`` (Docker)?

    * No Docker dependency at synth time — runs anywhere uv runs.
    * Lambda needs ``handler.py`` at the zip root, with ``sbc_config/`` next
      to it on ``sys.path``. ``shutil.copytree`` builds exactly that layout.
    * CDK hashes file content (not mtimes), so the asset hash is stable
      across synth runs as long as the source files are unchanged.
    """
    staging = Path(tempfile.mkdtemp(prefix="cdk-provision-device-"))
    shutil.copy(HANDLER_PATH, staging / "handler.py")

    iot_src = REPO_ROOT / "sbc_config" / "modules" / "iot"
    iot_dest = staging / "sbc_config" / "modules" / "iot"
    iot_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        iot_src,
        iot_dest,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "mqtt5.py",  # awsiotsdk not in Lambda runtime; module is laptop/Pi-only.
            "greengrass_install.py",  # subprocess + urllib installer; CLI-only.
        ),
    )

    # Empty package __init__.py files so import paths resolve.
    (staging / "sbc_config" / "__init__.py").write_text(
        '"""SBC Config — IoT lifecycle (Lambda-only subset)."""\n',
        encoding="utf-8",
    )
    (staging / "sbc_config" / "modules" / "__init__.py").write_text(
        '"""Lambda-bundled subset of sbc_config.modules."""\n',
        encoding="utf-8",
    )
    return staging


def _per_thing_policy_document(
    *,
    region: str,
    account: str,
    tes_role_alias: str | None,
) -> dict[str, Any]:
    """Per-Thing scoped IoT policy using IoT policy variables + Greengrass v2.

    Hello-world MQTT statements keep ``${iot:Connection.Thing.ThingName}``
    for the ``hello/<thingName>/*`` namespace (see ``docs/SBCC-INFRA-0001``).

    Greengrass needs multi-session **Connect** (``client/{thingName}*`` in the
    minimal AWS doc), shadow/job/health MQTT paths, ``greengrass:*`` service
    actions, and optional ``iot:AssumeRoleWithCertificate``. Those MQTT paths
    use the **same thing-name IoT variable** as hello-world so the document
    stays under **2048 characters** no matter how many Things the stack creates
    (enumerating one ARN set per Thing exceeds ``IOT_POLICY_DOCUMENT_MAX_CHARS``).

    See `Minimal AWS IoT policy for AWS IoT Greengrass V2 core devices
    <https://docs.aws.amazon.com/greengrass/v2/developerguide/device-auth.html#greengrass-core-minimal-iot-policy>`_.

    ``tes_role_alias`` — when set, the policy allows ``AssumeRoleWithCertificate``
    on ``arn:aws:iot:<region>:<account>:rolealias/<alias>``. The stack provisions
    the role + alias by default; set context ``createGreengrassTokenExchangeRole``
    to ``false`` to skip and optionally supply an external alias via
    ``greengrassTokenExchangeRoleAlias``.
    """
    tn = _THING_NAME_VAR
    publish_receive_resources = [
        f"arn:aws:iot:{region}:{account}:topic/$aws/things/{tn}/greengrass/health/json",
        f"arn:aws:iot:{region}:{account}:topic/$aws/things/{tn}/greengrassv2/health/json",
        f"arn:aws:iot:{region}:{account}:topic/$aws/things/{tn}/jobs/*",
        f"arn:aws:iot:{region}:{account}:topic/$aws/things/{tn}/shadow/*",
    ]
    subscribe_resources = [
        f"arn:aws:iot:{region}:{account}:topicfilter/$aws/things/{tn}/jobs/*",
        f"arn:aws:iot:{region}:{account}:topicfilter/$aws/things/{tn}/shadow/*",
    ]
    greengrass_connect_resource = f"arn:aws:iot:{region}:{account}:client/{tn}*"

    statements: list[dict[str, Any]] = [
        {
            "Sid": "ConnectAsOwnThing",
            "Effect": "Allow",
            "Action": "iot:Connect",
            "Resource": (
                f"arn:aws:iot:{region}:{account}:client/"
                "${iot:Connection.Thing.ThingName}"
            ),
            "Condition": {
                "Bool": {
                    "iot:Connection.Thing.IsAttached": "true",
                },
            },
        },
        {
            "Sid": "PublishOwnTopics",
            "Effect": "Allow",
            "Action": ["iot:Publish", "iot:Receive"],
            "Resource": (
                f"arn:aws:iot:{region}:{account}:topic/hello/"
                "${iot:Connection.Thing.ThingName}/*"
            ),
        },
        {
            "Sid": "SubscribeOwnTopicFilters",
            "Effect": "Allow",
            "Action": "iot:Subscribe",
            "Resource": (
                f"arn:aws:iot:{region}:{account}:topicfilter/hello/"
                "${iot:Connection.Thing.ThingName}/*"
            ),
        },
        {
            "Sid": "GgConnect",
            "Effect": "Allow",
            "Action": "iot:Connect",
            "Resource": greengrass_connect_resource,
            "Condition": {
                "Bool": {
                    "iot:Connection.Thing.IsAttached": "true",
                },
            },
        },
        {
            "Sid": "GgTopicsPubRecv",
            "Effect": "Allow",
            "Action": ["iot:Publish", "iot:Receive"],
            "Resource": publish_receive_resources,
        },
        {
            "Sid": "GgTopicsSub",
            "Effect": "Allow",
            "Action": "iot:Subscribe",
            "Resource": subscribe_resources,
        },
        {
            "Sid": "GgServiceApi",
            "Effect": "Allow",
            "Action": [
                "greengrass:GetComponentVersionArtifact",
                "greengrass:ResolveComponentCandidates",
                "greengrass:GetDeploymentConfiguration",
                "greengrass:ListThingGroupsForCoreDevice",
            ],
            "Resource": "*",
        },
    ]

    if tes_role_alias:
        statements.append(
            {
                "Sid": "GgTes",
                "Effect": "Allow",
                "Action": "iot:AssumeRoleWithCertificate",
                "Resource": (
                    f"arn:aws:iot:{region}:{account}:rolealias/{tes_role_alias}"
                ),
            }
        )

    return {"Version": "2012-10-17", "Statement": statements}


class IotHelloStack(cdk.Stack):
    """One stack, N Things — single shared policy + provisioning Lambda."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        thing_names: list[str],
        policy_name: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if not thing_names:
            msg = "IotHelloStack: at least one thingName is required."
            raise ValueError(msg)

        # ----------------------------------------------------------------
        # 0. Greengrass token exchange — IAM role + IoT role alias (default on).
        # ----------------------------------------------------------------
        # Set context ``createGreengrassTokenExchangeRole`` to false only if you
        # manage TES out of band; then optionally set ``greengrassTokenExchangeRoleAlias``
        # for an external alias name so the IoT policy still gets
        # ``iot:AssumeRoleWithCertificate``.
        skip_tes_infra = (
            self.node.try_get_context("createGreengrassTokenExchangeRole") is False
        )
        tes_alias: str | None = None
        greengrass_tes_role_alias_resource: iot.CfnRoleAlias | None = None
        if not skip_tes_infra:
            alias_ctx = self.node.try_get_context("greengrassTokenExchangeRoleAlias")
            alias_override = (
                alias_ctx if isinstance(alias_ctx, str) and alias_ctx else None
            )
            tes_role_alias_name = alias_override or DEFAULT_GREENGRASS_TES_ROLE_ALIAS

            tes_role = iam.Role(
                self,
                "GreengrassTokenExchangeRole",
                assumed_by=iam.ServicePrincipal("credentials.iot.amazonaws.com"),
                description=(
                    "Greengrass v2 token exchange - assumed via "
                    "iot:AssumeRoleWithCertificate on the device cert."
                ),
            )
            tes_role.add_to_policy(
                iam.PolicyStatement(
                    sid="GgTesCloudWatchLogs",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                        "logs:DescribeLogStreams",
                        "logs:DescribeLogGroups",
                    ],
                    resources=["*"],
                )
            )
            greengrass_tes_role_alias_resource = iot.CfnRoleAlias(
                self,
                "GreengrassTokenExchangeAlias",
                role_arn=tes_role.role_arn,
                role_alias=tes_role_alias_name,
            )
            tes_alias = tes_role_alias_name
        else:
            ext = self.node.try_get_context("greengrassTokenExchangeRoleAlias")
            tes_alias = ext if isinstance(ext, str) and ext else None

        # ----------------------------------------------------------------
        # 1. Per-Thing scoped IoT policy (one CFN resource for all Things).
        # ----------------------------------------------------------------
        policy = iot.CfnPolicy(
            self,
            "HelloWorldPolicy",
            policy_name=policy_name,
            policy_document=_per_thing_policy_document(
                region=self.region,
                account=self.account,
                tes_role_alias=tes_alias,
            ),
        )
        if greengrass_tes_role_alias_resource is not None:
            policy.node.add_dependency(greengrass_tes_role_alias_resource)

        # ----------------------------------------------------------------
        # 2. Custom-resource Lambda (Python 3.13) that owns cert lifecycle.
        # ----------------------------------------------------------------
        provision_role = iam.Role(
            self,
            "ProvisionLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description=(
                "Mint + lifecycle device certs and Secrets Manager PEM bundles. "
                "GetSecretValue is intentionally NOT granted - only humans/CI "
                "with narrow IAM should read PEMs."
            ),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole",
                ),
            ],
        )
        provision_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "iot:CreateKeysAndCertificate",
                    "iot:UpdateCertificate",
                    "iot:DeleteCertificate",
                    "iot:DescribeCertificate",
                    "iot:DescribeEndpoint",
                    "iot:AttachPolicy",
                    "iot:DetachPolicy",
                    "iot:ListAttachedPolicies",
                    "iot:AttachThingPrincipal",
                    "iot:DetachThingPrincipal",
                    "iot:ListThingPrincipals",
                    "iot:ListPrincipalThings",
                ],
                resources=["*"],
            )
        )
        provision_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:CreateSecret",
                    "secretsmanager:PutSecretValue",
                    "secretsmanager:UpdateSecret",
                    "secretsmanager:DescribeSecret",
                    "secretsmanager:DeleteSecret",
                    "secretsmanager:TagResource",
                ],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}"
                    f":secret:iot/things/*",
                ],
            )
        )

        # Explicit log groups — `log_retention` on Function/Provider is
        # deprecated in CDK >= 2.180 (uses an SDK call construct). LogGroup
        # is the current pattern.
        provision_log_group = logs.LogGroup(
            self,
            "ProvisionDeviceLambdaLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        provider_framework_log_group = logs.LogGroup(
            self,
            "ProvisionProviderFrameworkLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        provision_lambda = lambda_.Function(
            self,
            "ProvisionDeviceLambda",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="handler.on_event",
            code=lambda_.Code.from_asset(str(_stage_lambda_asset())),
            timeout=Duration.minutes(2),
            memory_size=256,
            role=provision_role,
            log_group=provision_log_group,
            description=(
                "Custom resource: CreateKeysAndCertificate + Secrets Manager PEM "
                "bundle + per-Thing attach/detach. Imports "
                "sbc_config.modules.iot.lifecycle (shared with `sbc iot "
                "decommission-thing`)."
            ),
        )

        provider = cr.Provider(
            self,
            "ProvisionProvider",
            on_event_handler=provision_lambda,
            provider_function_name=None,
            log_group=provider_framework_log_group,
            # framework_on_event_role / framework_complete_and_timeout_role
            # are intentionally left to CDK defaults — the deprecated `role`
            # prop is forbidden (see SBCC-INFRA-0001 § Currency guardrails).
        )

        # ----------------------------------------------------------------
        # 3. Per-Thing wiring — Thing + custom-resource invocation.
        # ----------------------------------------------------------------
        for thing_name in thing_names:
            self._wire_thing(
                thing_name=thing_name,
                policy=policy,
                provider=provider,
            )

        CfnOutput(
            self,
            "PolicyName",
            value=policy_name,
            description="Per-Thing-scoped IoT policy (shared across all Things).",
        )
        CfnOutput(
            self,
            "ThingNames",
            value=",".join(thing_names),
            description="IoT Things provisioned by this stack.",
        )
        if tes_alias is not None:
            CfnOutput(
                self,
                "GreengrassTokenExchangeRoleAlias",
                value=tes_alias,
                description=(
                    "Greengrass TES IoT role alias - export SBC_IOT_GG_TES_ROLE_ALIAS "
                    "to match for sbc iot install-greengrass."
                ),
            )

    def _wire_thing(
        self,
        *,
        thing_name: str,
        policy: iot.CfnPolicy,
        provider: cr.Provider,
    ) -> None:
        """Create the Thing + custom-resource invocation for a single device."""
        # Logical id must be CloudFormation-safe; thingName is operator-facing
        # and may contain hyphens that aren't valid in logical ids.
        construct_id = "Thing-" + thing_name.replace("-", "")

        thing = iot.CfnThing(
            self,
            construct_id,
            thing_name=thing_name,
        )
        thing.apply_removal_policy(RemovalPolicy.DESTROY)

        secret_id = f"iot/things/{thing_name}/credentials"
        provision = CustomResource(
            self,
            f"Provision-{thing_name.replace('-', '')}",
            service_token=provider.service_token,
            properties={
                "ThingName": thing_name,
                "PolicyName": policy.policy_name,
                "SecretId": secret_id,
                # Bumping this string forces CFN to invoke `Update` and (per
                # plan) the handler treats CertVersion change as a key-rotation
                # signal that triggers Replace via PhysicalResourceId change.
                "CertVersion": "1",
            },
        )
        provision.node.add_dependency(thing)
        provision.node.add_dependency(policy)

        CfnOutput(
            self,
            f"SecretId-{construct_id}",
            value=secret_id,
            description=(
                f"Secrets Manager id for {thing_name}. Read with "
                "`sbc iot fetch-credentials --thing-name "
                f"{thing_name}`."
            ),
        )
