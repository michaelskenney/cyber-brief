"""Tests for macOS Keychain secrets helper."""
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from keychain import get_secret, get_secret_with_fallback


class TestGetSecret:
    """Tests for the get_secret function."""

    @patch("keychain.subprocess.run")
    def test_returns_secret_from_keychain(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="my-api-key\n")
        result = get_secret("cyber-brief", "EXA_API_KEY")
        assert result == "my-api-key"
        mock_run.assert_called_once_with(
            ["security", "find-generic-password", "-s", "cyber-brief", "-a", "EXA_API_KEY", "-w"],
            capture_output=True,
            text=True,
        )

    @patch("keychain.subprocess.run")
    def test_strips_whitespace(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="  spaced-key  \n")
        result = get_secret("cyber-brief", "EXA_API_KEY")
        assert result == "spaced-key"

    @patch("keychain.subprocess.run")
    def test_raises_on_keychain_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=44, stdout="", stderr="not found")
        with pytest.raises(RuntimeError, match="Keychain lookup failed"):
            get_secret("cyber-brief", "MISSING_KEY")

    @patch.dict("os.environ", {"EXA_API_KEY": "env-fallback-key"})
    @patch("keychain.subprocess.run")
    def test_fallback_returns_env_var(self, mock_run):
        mock_run.return_value = MagicMock(returncode=44, stdout="", stderr="not found")
        result = get_secret_with_fallback("cyber-brief", "EXA_API_KEY")
        assert result == "env-fallback-key"

    @patch.dict("os.environ", {}, clear=True)
    @patch("keychain.subprocess.run")
    def test_fallback_raises_when_no_env_var(self, mock_run):
        mock_run.return_value = MagicMock(returncode=44, stdout="", stderr="not found")
        with pytest.raises(RuntimeError, match="not found in Keychain or environment"):
            get_secret_with_fallback("cyber-brief", "MISSING_KEY")
