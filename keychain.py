"""macOS Keychain secrets helper.

Reads secrets from the macOS login keychain using the `security` CLI.
Falls back to environment variables during migration.
"""

import os
import subprocess


def get_secret(service: str, account: str) -> str:
    """Read a secret from macOS Keychain.

    Args:
        service: Keychain service name (e.g., 'cyber-brief')
        account: Keychain account name (e.g., 'EXA_API_KEY')

    Returns:
        The secret value.

    Raises:
        RuntimeError: If the secret is not found in Keychain.
    """
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Keychain lookup failed for {service}/{account}")
    return result.stdout.strip()


def get_secret_with_fallback(service: str, account: str) -> str:
    """Read a secret from Keychain, falling back to environment variable.

    Tries Keychain first. If that fails, checks os.environ[account].
    This supports a gradual migration from .env to Keychain.

    Args:
        service: Keychain service name
        account: Keychain account name (also used as env var name)

    Returns:
        The secret value.

    Raises:
        RuntimeError: If the secret is not found in Keychain or environment.
    """
    try:
        return get_secret(service, account)
    except RuntimeError:
        value = os.environ.get(account)
        if value is None:
            raise RuntimeError(
                f"{account} not found in Keychain or environment. "
                f"Add it with: security add-generic-password -s {service} -a {account} -w 'your-value'"
            )
        return value
