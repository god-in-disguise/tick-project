from __future__ import annotations

from dataclasses import dataclass


class CustodyError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GeneratedWallet:
    address: str
    encrypted_private_key: bytes


class SecretCipher:
    def __init__(self, key: str) -> None:
        if not key:
            raise CustodyError("CUSTODY_PRIVATE_KEY_ENCRYPTION_KEY is not configured")
        from cryptography.fernet import Fernet

        self._fernet = Fernet(key.encode())

    @staticmethod
    def generate_key() -> str:
        from cryptography.fernet import Fernet

        return Fernet.generate_key().decode()

    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode())

    def decrypt(self, encrypted_value: bytes) -> str:
        return self._fernet.decrypt(encrypted_value).decode()


class PrivateKeyCipher(SecretCipher):
    pass


class PlatformWalletFactory:
    def __init__(self, cipher: PrivateKeyCipher) -> None:
        self._cipher = cipher

    def create_arbitrum_wallet(self) -> GeneratedWallet:
        from eth_account import Account

        account = Account.create()
        return GeneratedWallet(
            address=account.address,
            encrypted_private_key=self._cipher.encrypt(account.key.hex()),
        )
