from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from price_cycle.providers import (
    EnvironmentCredentialResolver,
    ProviderConfigError,
    load_provider_config,
)


EXIT_OK = 0
EXIT_CONFIG = 3


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        self.print_usage(sys.stderr)
        self.exit(
            EXIT_CONFIG,
            "Configuration error [CLI_ARGUMENT_INVALID]: "
            "invalid command arguments\n"
            "No credential value was read and no network request was made.\n",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(
        prog="price-cycle-validate-provider-config",
        description=(
            "Validate provider routing and credential references without "
            "making a network request."
        ),
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Explicit provider TOML path; no file is discovered automatically",
    )
    parser.add_argument(
        "--check-credentials",
        action="store_true",
        help=(
            "Check whether code-owned credential environment variables exist; "
            "never print their values"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        configuration = load_provider_config(Path(arguments.config))
    except ProviderConfigError as error:
        print(
            f"Configuration error [{error.code}]: {error}",
            file=sys.stderr,
        )
        print("No credential value was read and no network request was made.")
        return EXIT_CONFIG

    resolver = EnvironmentCredentialResolver()
    summary = configuration.public_summary(
        check_credentials=arguments.check_credentials,
        resolver=resolver,
    )
    print("Provider configuration is valid.")
    print("No network request was made.")
    print(f"Schema version: {summary['schema_version']}")
    print(
        "Network permission in config: "
        + ("enabled" if summary["allow_network"] else "disabled")
    )
    print(f"Configuration fingerprint: {summary['fingerprint']}")
    print("Routes:")
    for route in summary["routes"]:
        provider_order = ", ".join(route["provider_order"])
        print(
            f"- {route['data_kind']}.{route['market']}: {provider_order}"
        )
    print("Providers:")
    for provider in summary["providers"]:
        state = "enabled" if provider["enabled"] else "disabled"
        availability = (
            "implemented" if provider["implemented"] else "planned-only"
        )
        print(
            f"- {provider['provider_id']}: {state}, {availability}, "
            f"{provider['access_mode']}, {provider['assurance_mode']}"
        )
        for credential in provider["credentials"]:
            print(
                "  credential "
                f"{credential['name']}: "
                f"{credential['environment_variable']} "
                f"({credential['status']})"
            )

    if arguments.check_credentials:
        missing = configuration.missing_enabled_credentials(resolver)
        if missing:
            print(
                "Credential error [CREDENTIAL_ENV_MISSING]: "
                "missing environment variables: "
                + ", ".join(missing),
                file=sys.stderr,
            )
            print("No credential value was printed.", file=sys.stderr)
            return EXIT_CONFIG
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
