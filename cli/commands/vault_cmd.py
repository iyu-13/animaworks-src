from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI subcommand for vault key-value storage.

Usage via animaworks-tool:
    animaworks-tool vault get KEY
    animaworks-tool vault store KEY VALUE
    animaworks-tool vault list
"""

import argparse
import json
import os
import sys
from pathlib import Path


def cmd_vault(args: argparse.Namespace) -> None:
    """Dispatch vault subcommand."""
    anima_dir_str = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
    if not anima_dir_str:
        print("Error: ANIMAWORKS_ANIMA_DIR not set", file=sys.stderr)
        sys.exit(1)

    anima_dir = Path(anima_dir_str)
    if not anima_dir.is_dir():
        print(f"Error: anima_dir not found: {anima_dir}", file=sys.stderr)
        sys.exit(1)

    namespace = anima_dir.name

    from core.config.vault import get_vault_manager

    vm = get_vault_manager()

    sub = getattr(args, "vault_command", None)
    if sub == "get":
        _cmd_get(args, vm, namespace)
    elif sub == "store":
        _cmd_store(args, vm, namespace)
    elif sub == "list":
        _cmd_list(vm, namespace)
    else:
        print("Usage: animaworks-tool vault {get|store|list}", file=sys.stderr)
        sys.exit(1)


def _cmd_get(args: argparse.Namespace, vm, namespace: str) -> None:
    key = getattr(args, "key", "")
    if not key:
        print("Error: key is required", file=sys.stderr)
        sys.exit(1)

    value = vm.get(namespace, key)
    if value is None:
        print(f"Error: key not found: {key}", file=sys.stderr)
        sys.exit(1)

    result = {"key": key, "value": value}
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_store(args: argparse.Namespace, vm, namespace: str) -> None:
    key = getattr(args, "key", "")
    value = getattr(args, "value", "")
    if not key:
        print("Error: key is required", file=sys.stderr)
        sys.exit(1)

    vm.store(namespace, key, value)
    result = {"key": key, "stored": True}
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_list(vm, namespace: str) -> None:
    data = vm.load_vault()
    keys = sorted(data.get(namespace, {}).keys())
    print(json.dumps(keys, ensure_ascii=False, indent=2))


def register_vault_command(subparsers) -> None:
    """Register the vault subcommand under animaworks-tool."""
    p_vault = subparsers.add_parser("vault", help="Anima-scoped key-value vault")
    vault_sub = p_vault.add_subparsers(dest="vault_command")

    p_get = vault_sub.add_parser("get", help="Get a value by key")
    p_get.add_argument("key", help="Key to retrieve")

    p_store = vault_sub.add_parser("store", help="Store a key-value pair")
    p_store.add_argument("key", help="Key to store")
    p_store.add_argument("value", help="Value to store")

    vault_sub.add_parser("list", help="List all keys in anima namespace")

    p_vault.set_defaults(func=cmd_vault)
