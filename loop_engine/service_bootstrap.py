"""Fixed sealed service entrypoint; never loads code from the project checkout."""

import argparse
import json
import sys

from loop_engine.service_identity import Deployment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("review", "merge"), required=True)
    parser.add_argument("--manifest-hash", required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    deployment = Deployment(args.manifest_hash)
    deployment.require_role(args.role)
    if not args.worker:
        from loop_engine.service_host import scm

        scm(deployment, args.role)
        return 0
    from loop_engine.github_app import AppConnectionError
    from loop_engine.planning import bounded_json
    from loop_engine.service_worker import dispatch

    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        return 2
    try:
        request = bounded_json(raw.decode("utf-8"), maximum=65536)
        if not isinstance(request, dict) or set(request) != {"peer", "body"}:
            return 2
        result = dispatch(deployment, args.role, request["peer"], request["body"])
        print(json.dumps(result))
        return 0
    except AppConnectionError as error:
        print(json.dumps({"connection_error": error.public()}))
        return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Never emit arbitrary error/traceback content from a credential consumer.
        print('{"status":"blocked","reason":"service_operation_failed"}')
        raise SystemExit(2) from None
