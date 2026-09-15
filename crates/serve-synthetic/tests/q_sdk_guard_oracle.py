#!/usr/bin/env python3
"""Independent named guard assertions around unchanged fake transports."""
import argparse
import importlib.util
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", required=True)
    parser.add_argument("--case", required=True, choices=["cloud-destination", "redirect-follow"])
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("q_sdk_client", Path(args.client))
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    try:
        client.prove_destination_and_redirect_guards()
    except AssertionError as exc:
        if args.case == "cloud-destination" and str(exc) == "fake cloud destination was accepted":
            raise AssertionError("Q_CLOUD_DESTINATION_ACCEPTED") from exc
        raise
    except RuntimeError as exc:
        if args.case == "redirect-follow" and str(exc) == "SDK destination must use HTTP loopback":
            frames = []
            trace = exc.__traceback__
            while trace is not None:
                frames.append(trace.tb_frame.f_code.co_name)
                trace = trace.tb_next
            if "prove_destination_and_redirect_guards" in frames and "require_loopback" in frames:
                raise AssertionError("Q_REDIRECT_FOLLOW_ATTEMPT") from exc
        raise
    print("Q_SDK_GUARD_PRISTINE_PASS")


if __name__ == "__main__":
    main()
