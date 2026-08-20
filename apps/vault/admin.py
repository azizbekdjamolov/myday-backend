"""Django admin registration for the Vault.

Deliberately NOT registered: VaultItem and VaultFile are private user data
and must never appear in the Django admin, where admins could casually read
decrypted credentials.
"""

# Intentionally empty.