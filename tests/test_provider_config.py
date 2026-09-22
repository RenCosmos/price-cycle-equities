from __future__ import annotations

from dataclasses import is_dataclass
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import traceback
import unittest

from tests.helpers import SCRIPT_ROOT

from price_cycle.models import Market
from price_cycle.providers import (
    CredentialSpec,
    CredentialUnavailableError,
    DataAssuranceMode,
    EnvironmentCredentialResolver,
    ProviderAccessMode,
    ProviderCatalog,
    ProviderConfigError,
    ProviderConfiguration,
    ProviderDescriptor,
    ProviderRoute,
    ProviderSettings,
    SecretValue,
    load_provider_config,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = REPO_ROOT / "examples" / "provider-config.toml.example"
VALIDATOR = SCRIPT_ROOT / "validate_provider_config.py"


def write_config(directory: str, content: str, name: str = "providers.toml") -> Path:
    path = Path(directory) / name
    path.write_text(content, encoding="utf-8")
    return path


def local_catalog() -> ProviderCatalog:
    return ProviderCatalog(
        (
            ProviderDescriptor(
                provider_id="first",
                assurance_mode=DataAssuranceMode.PROVIDER_VERIFIED,
                access_mode=ProviderAccessMode.LOCAL,
                implemented=True,
                credentials=(),
                supported_markets=(Market.CN,),
                data_kinds=("daily_bars",),
            ),
            ProviderDescriptor(
                provider_id="second",
                assurance_mode=DataAssuranceMode.PROVIDER_VERIFIED,
                access_mode=ProviderAccessMode.LOCAL,
                implemented=True,
                credentials=(),
                supported_markets=(Market.CN,),
                data_kinds=("daily_bars",),
            ),
        )
    )


def remote_catalog() -> ProviderCatalog:
    return ProviderCatalog(
        (
            ProviderDescriptor(
                provider_id="mock_remote",
                assurance_mode=DataAssuranceMode.PROVIDER_VERIFIED,
                access_mode=ProviderAccessMode.REMOTE,
                implemented=True,
                credentials=(
                    CredentialSpec("token", "PRICE_CYCLE_MOCK_TOKEN"),
                ),
                supported_markets=(Market.US,),
                data_kinds=("daily_bars",),
            ),
        )
    )


class ProviderConfigurationTests(unittest.TestCase):
    def test_example_is_offline_and_routes_both_markets_to_manual_csv(self) -> None:
        configuration = load_provider_config(EXAMPLE_CONFIG)
        self.assertFalse(configuration.allow_network)
        self.assertEqual(
            configuration.route_for("daily_bars", Market.CN),
            ("manual_csv",),
        )
        self.assertEqual(
            configuration.route_for("daily_bars", Market.US),
            ("manual_csv",),
        )
        self.assertTrue(configuration.provider("manual_csv").enabled)
        self.assertFalse(configuration.provider("tushare").enabled)
        self.assertFalse(configuration.provider("eodhd").enabled)

    def test_config_is_strict_and_does_not_echo_literal_secret(self) -> None:
        marker = "fixture-secret-value"
        cases = (
            (
                "schema_version = 1\nunknown = true\n",
                "CONFIG_UNKNOWN_KEY",
            ),
            (
                "schema_version = [\n",
                "CONFIG_TOML_INVALID",
            ),
            (
                """
schema_version = 1
[providers.unknown]
enabled = true
[routes.daily_bars]
CN = ["unknown"]
""",
                "UNKNOWN_PROVIDER",
            ),
            (
                f"""
schema_version = 1
[providers.manual_csv]
enabled = true
token = "{marker}"
[routes.daily_bars]
CN = ["manual_csv"]
""",
                "CONFIG_UNKNOWN_KEY",
            ),
        )
        for index, (content, expected_code) in enumerate(cases):
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as directory:
                path = write_config(directory, content, f"case-{index}.toml")
                with self.assertRaises(ProviderConfigError) as caught:
                    load_provider_config(path)
                self.assertEqual(caught.exception.code, expected_code)
                self.assertNotIn(marker, str(caught.exception))

    def test_untrusted_toml_identifiers_are_never_echoed(self) -> None:
        marker = "fixture-secret-value"
        cases = (
            f'''schema_version = 1\n"{marker}" = true\n''',
            f'''
schema_version = 1
[providers."{marker}"]
enabled = true
[routes.daily_bars]
CN = ["manual_csv"]
''',
            f'''
schema_version = 1
[providers.manual_csv]
enabled = true
[routes."{marker}"]
CN = ["manual_csv"]
''',
            f'''
schema_version = 1
[providers.manual_csv]
enabled = true
[routes.daily_bars]
"{marker}" = ["manual_csv"]
''',
            f'''
schema_version = 1
[providers.manual_csv]
enabled = true
[routes.daily_bars]
CN = ["{marker}"]
''',
        )
        for index, content in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                path = write_config(directory, content, f"marker-{index}.toml")
                with self.assertRaises(ProviderConfigError) as caught:
                    load_provider_config(path)
                self.assertNotIn(marker, str(caught.exception))

    def test_public_configuration_objects_cannot_bypass_type_checks(self) -> None:
        providers = (ProviderSettings("manual_csv", True),)
        routes = (
            ProviderRoute("daily_bars", Market.CN, ("manual_csv",)),
        )
        invalid_configurations = (
            {
                "schema_version": True,
                "allow_network": False,
                "providers": providers,
                "routes": routes,
            },
            {
                "schema_version": 1,
                "allow_network": "false",
                "providers": providers,
                "routes": routes,
            },
            {
                "schema_version": 1,
                "allow_network": False,
                "providers": (),
                "routes": routes,
            },
            {
                "schema_version": 1,
                "allow_network": False,
                "providers": providers,
                "routes": (),
            },
        )
        for arguments in invalid_configurations:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ProviderConfigError):
                    ProviderConfiguration(**arguments)
        with self.assertRaises(ValueError):
            ProviderSettings("manual_csv", "true")
        with self.assertRaises(ValueError):
            ProviderRoute("daily_bars", "CN", ("manual_csv",))

    def test_invalid_routes_and_unimplemented_provider_fail_closed(self) -> None:
        cases = (
            (
                """
schema_version = 1
[providers.manual_csv]
enabled = false
[routes.daily_bars]
CN = ["manual_csv"]
""",
                "ROUTE_PROVIDER_DISABLED",
            ),
            (
                """
schema_version = 1
[providers.manual_csv]
enabled = true
[routes.daily_bars]
ZZ = ["manual_csv"]
""",
                "ROUTE_MARKET_UNKNOWN",
            ),
            (
                """
schema_version = 1
allow_network = true
[providers.tushare]
enabled = true
[routes.daily_bars]
CN = ["tushare"]
""",
                "PROVIDER_NOT_AVAILABLE",
            ),
        )
        for index, (content, expected_code) in enumerate(cases):
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as directory:
                path = write_config(directory, content, f"route-{index}.toml")
                with self.assertRaises(ProviderConfigError) as caught:
                    load_provider_config(path)
                self.assertEqual(caught.exception.code, expected_code)

    def test_missing_file_error_exposes_no_user_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture-residual-secret.toml"
            with self.assertRaises(ProviderConfigError) as caught:
                load_provider_config(path)
            self.assertEqual(caught.exception.code, "CONFIG_NOT_FOUND")
            self.assertNotIn(path.name, str(caught.exception))
            self.assertNotIn(str(path.parent), str(caught.exception))
            rendered = "".join(
                traceback.format_exception(caught.exception)
            )
            self.assertNotIn(path.name, rendered)
            self.assertNotIn(str(path.parent), rendered)
            self.assertIsNone(caught.exception.__context__)

    def test_fingerprint_is_canonical_but_preserves_fallback_order(self) -> None:
        first = """
schema_version = 1
allow_network = false
[providers.first]
enabled = true
[providers.second]
enabled = true
[routes.daily_bars]
CN = ["first", "second"]
"""
        reordered_tables = """
allow_network = false
schema_version = 1
[providers.second]
enabled = true
[providers.first]
enabled = true
[routes.daily_bars]
CN = ["first", "second"]
"""
        reversed_route = first.replace(
            '["first", "second"]',
            '["second", "first"]',
        )
        with tempfile.TemporaryDirectory() as directory:
            paths = (
                write_config(directory, first, "first.toml"),
                write_config(directory, reordered_tables, "second.toml"),
                write_config(directory, reversed_route, "third.toml"),
            )
            configs = tuple(
                load_provider_config(path, catalog=local_catalog())
                for path in paths
            )
        self.assertEqual(configs[0].fingerprint, configs[1].fingerprint)
        self.assertNotEqual(configs[0].fingerprint, configs[2].fingerprint)

    def test_network_permission_is_required_for_a_remote_route(self) -> None:
        content = """
schema_version = 1
allow_network = false
[providers.mock_remote]
enabled = true
[routes.daily_bars]
US = ["mock_remote"]
"""
        with tempfile.TemporaryDirectory() as directory:
            path = write_config(directory, content)
            with self.assertRaises(ProviderConfigError) as caught:
                load_provider_config(path, catalog=remote_catalog())
        self.assertEqual(caught.exception.code, "NETWORK_DISABLED")

    def test_secret_wrapper_and_summary_do_not_disclose_value(self) -> None:
        marker = "fixture-credential-value"
        spec = CredentialSpec("token", "PRICE_CYCLE_MOCK_TOKEN")
        resolver = EnvironmentCredentialResolver(
            {"PRICE_CYCLE_MOCK_TOKEN": marker}
        )
        secret = resolver.resolve(spec)
        self.assertIsInstance(secret, SecretValue)
        self.assertFalse(is_dataclass(secret))
        self.assertEqual(str(secret), "[REDACTED]")
        self.assertNotIn(marker, repr(secret))
        self.assertEqual(secret.reveal(), marker)
        with self.assertRaises(TypeError):
            vars(secret)
        with self.assertRaises(TypeError):
            pickle.dumps(secret)
        with self.assertRaises(TypeError):
            pickle.dumps(resolver)

        content = """
schema_version = 1
allow_network = true
[providers.mock_remote]
enabled = true
[routes.daily_bars]
US = ["mock_remote"]
"""
        with tempfile.TemporaryDirectory() as directory:
            path = write_config(directory, content)
            configuration = load_provider_config(
                path,
                catalog=remote_catalog(),
            )
        fingerprint = configuration.fingerprint
        summary = configuration.public_summary(
            check_credentials=True,
            resolver=resolver,
        )
        self.assertNotIn(marker, str(summary))
        self.assertNotIn(marker, fingerprint)
        self.assertEqual(
            summary["providers"][0]["credentials"][0]["status"],
            "available",
        )
        changed_resolver = EnvironmentCredentialResolver(
            {"PRICE_CYCLE_MOCK_TOKEN": "different-secret"}
        )
        self.assertEqual(configuration.fingerprint, fingerprint)
        self.assertEqual(
            configuration.missing_enabled_credentials(changed_resolver),
            (),
        )

    def test_missing_or_blank_credential_is_reported_by_name_only(self) -> None:
        spec = CredentialSpec("token", "PRICE_CYCLE_MOCK_TOKEN")
        for environment in ({}, {"PRICE_CYCLE_MOCK_TOKEN": "   "}):
            with self.subTest(environment=environment):
                resolver = EnvironmentCredentialResolver(environment)
                self.assertFalse(resolver.is_available(spec))
                with self.assertRaises(CredentialUnavailableError) as caught:
                    resolver.resolve(spec)
                self.assertIn("PRICE_CYCLE_MOCK_TOKEN", str(caught.exception))

    def test_validator_output_never_echoes_environment_value(self) -> None:
        marker = "fixture-validator-secret"
        environment = os.environ.copy()
        environment["PRICE_CYCLE_TUSHARE_TOKEN"] = marker
        completed = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--config",
                str(EXAMPLE_CONFIG),
                "--check-credentials",
            ],
            cwd=REPO_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        combined = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, combined)
        self.assertIn("No network request was made.", combined)
        self.assertNotIn(marker, combined)

    def test_validator_handles_invalid_route_without_traceback_or_path(self) -> None:
        marker = "fixture invalid secret"
        content = f'''
schema_version = 1
[providers.manual_csv]
enabled = true
[routes.daily_bars]
CN = ["{marker}"]
'''
        with tempfile.TemporaryDirectory() as directory:
            path = write_config(directory, content)
            completed = subprocess.run(
                [sys.executable, str(VALIDATOR), "--config", str(path)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            combined = completed.stdout + completed.stderr
            self.assertEqual(completed.returncode, 3, combined)
            self.assertNotIn("Traceback", combined)
            self.assertNotIn(marker, combined)
            self.assertNotIn(str(path.parent), combined)

    def test_validator_does_not_echo_unknown_cli_secret(self) -> None:
        marker = "fixture-cli-secret"
        completed = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--config",
                str(EXAMPLE_CONFIG),
                "--token",
                marker,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        combined = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 3, combined)
        self.assertNotIn(marker, combined)
        self.assertNotIn("Traceback", combined)


if __name__ == "__main__":
    unittest.main()
