from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eth_account import Account

from tick_mvp.core.config import get_settings
from tick_mvp.domain.states import WalletStatus, WalletType
from tick_mvp.infrastructure.custody import PrivateKeyCipher
from tick_mvp.infrastructure.database import create_session_factory, session_scope
from tick_mvp.infrastructure.models import WalletAccount
from tick_mvp.infrastructure.sqlalchemy_store import SQLAlchemyStore


def main() -> None:
    args = parse_args()
    private_key = os.getenv(args.private_key_env)
    if not private_key:
        raise SystemExit(f"{args.private_key_env} is not set")

    settings = get_settings()
    account = Account.from_key(private_key)
    cipher = PrivateKeyCipher(settings.custody_private_key_encryption_key)
    store = SQLAlchemyStore(default_venue=settings.default_venue)
    user, _ = store.upsert_google_user(
        provider_subject=f"dev:{args.user_id}",
        email=f"{args.user_id}@dev.tick.local",
        display_name=args.user_id,
        avatar_url=None,
        chain_id=settings.arb_chain_id,
        custody_provider=settings.custody_provider,
    )

    now = datetime.now(UTC)
    session_factory = create_session_factory()
    with session_scope(session_factory) as session:
        existing_for_address = (
            session.query(WalletAccount)
            .filter(WalletAccount.chain_id == settings.arb_chain_id, WalletAccount.address == account.address)
            .one_or_none()
        )
        if existing_for_address is not None and existing_for_address.user_id != user.id:
            raise SystemExit(f"wallet address already belongs to another user: {existing_for_address.user_id}")

        wallet = (
            session.query(WalletAccount)
            .filter(WalletAccount.user_id == user.id, WalletAccount.status == WalletStatus.ACTIVE.value)
            .order_by(WalletAccount.created_at.asc())
            .first()
        )
        if wallet is None:
            wallet = WalletAccount(
                id=f"wallet_{os.urandom(16).hex()}",
                user_id=user.id,
                chain_id=settings.arb_chain_id,
                address=account.address,
                wallet_type=WalletType.PLATFORM_CUSTODY.value,
                status=WalletStatus.ACTIVE.value,
                custody_provider=settings.custody_provider,
                custody_key_ref=f"encrypted_postgres:{user.id}",
                encrypted_private_key=cipher.encrypt(private_key),
                gas_wallet=False,
                payload={},
                created_at=now,
                updated_at=now,
            )
            session.add(wallet)
        else:
            wallet.chain_id = settings.arb_chain_id
            wallet.address = account.address
            wallet.wallet_type = WalletType.PLATFORM_CUSTODY.value
            wallet.status = WalletStatus.ACTIVE.value
            wallet.custody_provider = settings.custody_provider
            wallet.custody_key_ref = f"encrypted_postgres:{user.id}"
            wallet.encrypted_private_key = cipher.encrypt(private_key)
            wallet.updated_at = now
        session.flush()
        wallet_id = wallet.id

    print(f"USER_ID={args.user_id}")
    print(f"ADDRESS={account.address}")
    print(f"WALLET_ID={wallet_id}")
    print("IMPORTED=true")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a dev wallet private key into the local TICK backend database.")
    parser.add_argument("--user-id", default="funded-dev")
    parser.add_argument("--private-key-env", default="DEV_WALLET_PRIVATE_KEY")
    return parser.parse_args()


if __name__ == "__main__":
    main()
