# SBCC-INFRA-0002 — AWS IoT Core network & egress (IT briefing)

**Audience:** IT directors, network/security stewards, site operators approving firewall and egress policy.

**Companion:** Technical stack and CLI flow live in **[SBCC-INFRA-0001](SBCC-INFRA-0001-iot-hello-world-cdk.md)** (CDK stack, Secrets Manager bundle, `sbc iot` commands).

---

## Executive summary

- Field devices connect to **AWS IoT Core** using **encrypted MQTT** (**TLS**) and **per-device certificates** (**mutual TLS**). Authorization is enforced in **AWS** (Thing policies), not by trusting a device’s IP address.
- **Typical MQTT traffic is outbound-only** from the device: no inbound open port on the device is required for standard publish/subscribe.
- **Transit** for that pattern uses the **normal routed internet** from the device’s network toward **AWS in the chosen Region** unless you deliberately add **private WAN / VPN / VPC endpoints** ([PrivateLink overview](https://docs.aws.amazon.com/iot/latest/developerguide/IoTCore-VPC.html)).
- **Egress policies** should prefer **FQDN + port + direction** for HTTPS to AWS APIs; **MQTT on TCP 8883** depends on whether your firewall stack supports hostname or application-aware rules (see below).

---

## What we are asking networks to permit

### Field device (example: Single Board Computer (SBC), runtime only)

Assume credentials and **`iotDataEndpoint`** are already on the device (provisioned offline or via your process). Matches **`sbc iot mqtt-test`** behavior: **MQTT 5 over TLS** to the ATS data endpoint host ([`mqtt5_client_builder.mtls_from_path`](../sbc_config/modules/iot/mqtt5.py)).

| Dimension                    | Typical requirement                                                              |
| ---------------------------- | -------------------------------------------------------------------------------- |
| Direction                    | **Egress only**                                                                  |
| Protocol                     | **TLS** (MQTT over TLS)                                                          |
| Port                         | **8883/tcp** to the **`iotDataEndpoint`** hostname stored with the device bundle |
| DNS                          | Resolve that hostname (tenant DNS / split DNS as needed)                         |
| Inbound from cloud to device | **Not required** for this MQTT client pattern                                    |

The **`iotDataEndpoint`** value is **account- and Region-specific** (e.g. `*.iot.us-west-2.amazonaws.com`-style). Use the **exact hostname** from provisioning, not a generic guess.

**Optional:** If you later move clients to **MQTT over 443** (ALPN), add **443/tcp** to the same logical destination; the current repo default is **8883**.

### Operator laptop or CI (provisioning, secrets, debugging)

Boto3 and AWS CLI use **HTTPS** to regional **AWS APIs**. For the same **Region** as the stack (spike default: **`us-west-2`**), plan at least:

| Use                      | Port        | Example destination (verify in your environment)     |
| ------------------------ | ----------- | ---------------------------------------------------- |
| Secrets Manager          | **443/tcp** | `secretsmanager.us-west-2.amazonaws.com`             |
| IoT control plane        | **443/tcp** | `iot.us-west-2.amazonaws.com`                        |
| AWS authentication (SSO) | **443/tcp** | Org-specific: `sts.*`, `sso.*`, `*.awsapps.com`, IdP |

**Identity Center / SSO** flows add **multiple HTTPS hostnames**; your identity team should confirm the exact set for **`aws sso login`**.

---

## Path diagram (default, no overlay VPN)

```text
[ Device ]  -- egress TLS :8883 -->  [ Site firewall / NAT / proxy ]
                                           |
                              ... routed internet ...
                                           |
                                           v
                               [ AWS IoT Core -- regional data endpoint ]

[ Operator PC ] -- egress HTTPS :443 --> [ Same site exit path ]
                                                   |
                                                   v
                                    [ Regional AWS APIs + SSO endpoints ]
```

Inside AWS after the TLS handshake, the broker path is **AWS-managed**; customers do not receive an internal hop list comparable to routing through **their own** VPC.

---

## Identity and policy (why this is not “IP trust”)

- Each device presents a **certificate** bound to an **IoT Thing** in **your AWS account**.
- **IoT policies** restrict **connect**, **publish**, **subscribe** (example pattern in INFRA-0001: **per-Thing** topic namespaces and **client ID** aligned to Thing name).
- **Revocation** is **per device** (detach/inactivate/delete cert workflows), not “block this whole subnet.”
- **Long-lived IAM user keys on the SBC** are **not** the primary transport pattern for MQTT; operators who read PEM material use narrow **IAM + Secrets Manager**, separate from fleet connectivity.

---

## Hostname allowlists versus IP allowlists

- **HTTPS to AWS APIs (443):** Hostname-based (or SWG URL) egress rules are **common** wherever **proxies** or **modern NGFW** FQDN objects exist.
- **MQTT (8883):** **Varies.** Some stacks offer **FQDN/Application-ID** egress; purely **layer-3 ACL** setups often force **managed IP prefix lists**.
- AWS publishes address ranges in **`ip-ranges.json`** ([AWS IP address ranges](https://docs.aws.amazon.com/general/latest/gr/aws-ip-ranges.html)). If policy **requires IPs**, assume **Regional** subsets and **change over time**: subscribe to [change notifications](https://docs.aws.amazon.com/general/latest/gr/subscribe-ip-space-notifications.html) or automate rule updates. **Do not** treat one static CIDR as permanent.

---

## When the default “internet egress” story is not enough

Use **additional architecture** (and update the security narrative) when requirements include:

| Requirement                                | Typical direction                                                                                                                               |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| No public routing to AWS from site         | **Site-to-site VPN**, **Direct Connect**, or **controlled egress** via your **own** VPC                                                         |
| Workloads in VPC must stay private         | **Interface VPC endpoints** for IoT data / APIs ([IoT + VPC endpoints](https://docs.aws.amazon.com/iot/latest/developerguide/IoTCore-VPC.html)) |
| Devices only reach you, not “raw” internet | **Backhaul** into **your** network (VPN, private APN, etc.), then **controlled** exit to AWS                                                    |

**PrivateLink / VPC endpoints** apply where traffic **enters or originates from a VPC** you control. Edge devices **do not** terminate PrivateLink by themselves; they need a **path into** such a network unless they use standard **internet TLS** to the regional endpoint.

**WireGuard (or any VPN)** is simply **tunneling**: it does not replace IoT **mTLS**; it changes **which router** speaks to the internet or to a corporate/VPC egress.

---

## TLS inspection (“SSL bump”)

Many corporates decrypt **HTTPS**. **MQTT over TLS on 8883** and AWS SDK HTTPS clients often **break** if decrypted or re-signed with unknown CAs.

**Recommendation:** **Do not decrypt** IoT MQTT to the configured **`iotDataEndpoint`**, or provide an **official exception** comparable to other cloud control-plane traffic.

---

## Copy-paste: egress policy ticket text

Customize **account**, **Region**, and **FQDN placeholders**.

```text
Title: Allow AWS IoT Core + AWS APIs -- project <PROJECT> account <ACCOUNT_ID> region us-west-2

A) Field devices (MQTT runtime)
   - Egress: TCP/8883 to <IOT_DATA_ENDPOINT_FQDN> (per device / per env; from Secrets Manager bundle field iotDataEndpoint)
   - DNS: resolve the above FQDN
   - No inbound required for MQTT client

B) Operators / automation
   - Egress: TCP/443 to secretsmanager.us-west-2.amazonaws.com, iot.us-west-2.amazonaws.com
   - Egress: TCP/443 per org AWS SSO / STS / IdP hostnames (identity team to list)

C) IP-only firewalls
   - Use AWS ip-ranges.json with automated updates; prefer Region-scoped entries where policy allows

D) TLS inspection
   - Exempt IoT data endpoint and AWS API traffic from SSL interception or expect connection failures
```

---

## Related links

- [SBCC-INFRA-0001 — IoT hello world (CDK + Lambda + Secrets Manager)](SBCC-INFRA-0001-iot-hello-world-cdk.md)
- [Using AWS IoT Core with interface VPC endpoints](https://docs.aws.amazon.com/iot/latest/developerguide/IoTCore-VPC.html)
- [AWS IP address ranges](https://docs.aws.amazon.com/general/latest/gr/aws-ip-ranges.html)
