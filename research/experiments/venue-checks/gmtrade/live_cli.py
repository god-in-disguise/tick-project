from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from solders.keypair import Keypair

from .config import ProbeConfig


ORDER_PATTERN = re.compile(r"^Order:\s+(\S+)", re.MULTILINE)
SIGNATURE_PATTERNS = (
    re.compile(r"signature\s*=\s*([1-9A-HJ-NP-Za-km-z]+)"),
    re.compile(r"\bat tx\s+([1-9A-HJ-NP-Za-km-z]+)"),
)
ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


@dataclass(frozen=True)
class CliResult:
    elapsed_ms: float
    stdout: str
    stderr: str
    order: str | None
    signature: str | None


def parse_json_output(stdout: str) -> object:
    cleaned = ANSI_PATTERN.sub("", stdout).strip()
    if not cleaned:
        raise RuntimeError("GMTrade CLI returned empty JSON output")
    decoder = json.JSONDecoder()
    first_candidates = [
        index for index in (cleaned.find("["), cleaned.find("{")) if index >= 0
    ]
    if not first_candidates:
        raise RuntimeError(f"GMTrade CLI returned no JSON: {cleaned[:500]!r}")
    start = min(first_candidates)
    try:
        value, _ = decoder.raw_decode(cleaned[start:])
        return value
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Could not parse GMTrade JSON output: {exc}; raw={cleaned[:1000]!r}"
        ) from exc


@contextmanager
def temporary_wallet_file(keypair: Keypair) -> Iterator[Path]:
    fd, name = tempfile.mkstemp(prefix="tick-gmtrade-", suffix=".json")
    path = Path(name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            json.dump(list(bytes(keypair)), handle)
        yield path
    finally:
        path.unlink(missing_ok=True)


def run_exchange(
    config: ProbeConfig,
    wallet_file: Path,
    arguments: Sequence[str],
    *,
    timeout_seconds: float = 90,
) -> CliResult:
    import time

    command = [
        str(config.cli_path),
        "--url",
        config.rpc_url,
        "--wallet",
        str(wallet_file),
        "exchange",
        *arguments,
    ]
    started = time.perf_counter()
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    combined = f"{result.stdout}\n{result.stderr}"
    order_match = ORDER_PATTERN.search(combined)
    signature = next(
        (
            match.group(1)
            for pattern in SIGNATURE_PATTERNS
            if (match := pattern.search(combined))
        ),
        None,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"GMTrade command failed: {detail}")
    if signature is None:
        raise RuntimeError("GMTrade command returned no transaction signature")
    return CliResult(
        elapsed_ms=elapsed_ms,
        stdout=result.stdout,
        stderr=result.stderr,
        order=order_match.group(1) if order_match else None,
        signature=signature,
    )


def read_actions(
    config: ProbeConfig,
    owner: str,
    action: str,
) -> object:
    if action not in {"positions", "orders"}:
        raise ValueError("action must be positions or orders")
    result = subprocess.run(
        [
            str(config.cli_path),
            "--url",
            config.rpc_url,
            "--output",
            "json",
            "exchange",
            "actions",
            "--owner",
            owner,
            f"--{action}",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Could not read GMTrade {action}: {detail}")
    return parse_json_output(result.stdout)
