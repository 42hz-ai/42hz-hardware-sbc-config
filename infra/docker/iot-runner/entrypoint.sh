#!/usr/bin/env sh
# entrypoint.sh — sbc-iot-runner container entry point
#
# Resolves the iot:Data-ATS endpoint for mqtt-test from the sidecar file
# written by `sbc iot fetch-credentials` on the operator laptop:
#
#     /data/aws-iot/endpoint.txt  (single line, e.g. abc123.iot.us-west-2.amazonaws.com)
#
# Priority for --endpoint (only injected when the first positional arg chain
# contains "mqtt-test" AND --endpoint is not already supplied by the caller):
#
#   1. Caller passes --endpoint explicitly → used as-is.
#   2. /data/aws-iot/endpoint.txt exists and is non-empty → read and prepend.
#   3. Neither → sbc passes the call to DescribeEndpoint (requires AWS creds).
#
# All other commands (describe-endpoint, fetch-credentials, etc.) are passed
# through unmodified.

set -e

ENDPOINT_FILE="${IOT_DATA_DIR:-/data/aws-iot}/endpoint.txt"

# Detect "iot mqtt-test" in the argument list without --endpoint already set.
_is_mqtt_test() {
    _saw_iot=0
    _saw_mqtt_test=0
    _saw_endpoint=0
    for _arg in "$@"; do
        case "$_arg" in
            iot)            _saw_iot=1 ;;
            mqtt-test)      [ "$_saw_iot" = 1 ] && _saw_mqtt_test=1 ;;
            --endpoint)     _saw_endpoint=1 ;;
            --endpoint=*)   _saw_endpoint=1 ;;
        esac
    done
    [ "$_saw_mqtt_test" = 1 ] && [ "$_saw_endpoint" = 0 ]
}

if _is_mqtt_test "$@" && [ -f "$ENDPOINT_FILE" ]; then
    _endpoint="$(cat "$ENDPOINT_FILE" | tr -d '[:space:]')"
    if [ -n "$_endpoint" ]; then
        # Inject --endpoint before the remaining args.
        # Find the position of "mqtt-test" and insert after it.
        _new_args=""
        _injected=0
        for _arg in "$@"; do
            _new_args="$_new_args $_arg"
            if [ "$_arg" = "mqtt-test" ] && [ "$_injected" = 0 ]; then
                _new_args="$_new_args --endpoint $_endpoint"
                _injected=1
            fi
        done
        # shellcheck disable=SC2086
        exec uv run sbc $( echo "$_new_args" | xargs )
    fi
fi

exec uv run sbc "$@"
