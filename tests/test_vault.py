"""Vault tests: encryption at rest, ownership isolation, reveal gating, files."""

from __future__ import annotations

import io

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.vault.models import VaultFile, VaultItem

from tests.conftest import PASSWORD

ITEMS = "/api/v1/vault/items/"
FILES = "/api/v1/vault/files/"
STATUS = "/api/v1/vault/status"


def _login(api, user):
    response = api.post("/api/v1/auth/login", {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 200
    csrf = api.cookies.get("myday_csrftoken")
    if csrf is not None:
        api.defaults["HTTP_X_CSRFTOKEN"] = csrf.value


def test_create_item_encrypts_at_rest(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = client.post(
        ITEMS,
        {"category": "accounts", "title": "Gmail", "username": "me@gmail.com", "password": "sup3rSecret", "notes": "n"},
        format="json",
    )
    assert response.status_code == 201

    raw = VaultItem.objects.get(id=response.data["id"])
    # Plaintext must never be stored.
    assert "sup3rSecret" not in raw.encrypted_password
    assert raw.encrypted_password.startswith("$")
    assert raw.encrypted_username.startswith("$")

    # List/retrieve never exposes secrets.
    detail = client.get(f"{ITEMS}{raw.id}/").data
    assert "password" not in detail
    assert "username" not in detail
    assert detail["has_password"] is True
    assert detail["has_username"] is True


def test_reveal_requires_password_and_unlock(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    item = VaultItem.objects.create(
        user=normal_user,
        category="accounts",
        title="GitHub",
        encrypted_username="octocat",
        encrypted_password="hunter2secret",
        encrypted_notes="two-factor note",
    )

    # Locked vault -> denied even with the right password.
    response = client.post(f"{ITEMS}{item.id}/reveal/", {"password": PASSWORD}, format="json")
    assert response.status_code == 403

    # Unlock with the correct password.
    response = client.post(f"{STATUS}?action=unlock", {"password": PASSWORD}, format="json")
    assert response.status_code == 200
    assert response.data["unlocked"] is True

    # Reveal with the wrong password -> denied.
    response = client.post(f"{ITEMS}{item.id}/reveal/", {"password": "WrongPass123!"}, format="json")
    assert response.status_code == 403

    # Reveal with the correct password -> plaintext, only for the owner.
    response = client.post(f"{ITEMS}{item.id}/reveal/", {"password": PASSWORD}, format="json")
    assert response.status_code == 200
    assert response.data["username"] == "octocat"
    assert response.data["password"] == "hunter2secret"
    assert response.data["notes"] == "two-factor note"


def test_lock_and_autolock(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    client.post(f"{STATUS}?action=unlock", {"password": PASSWORD}, format="json")

    response = client.post(f"{STATUS}?action=lock", {}, format="json")
    assert response.status_code == 200
    assert response.data["unlocked"] is False

    # Manual lock blocks reveal even with correct password.
    item = VaultItem.objects.create(user=normal_user, category="notes", title="locked")
    assert client.post(f"{ITEMS}{item.id}/reveal/", {"password": PASSWORD}, format="json").status_code == 403


def test_user_a_cannot_access_user_b_items(api, db, logged_in, normal_user):
    from apps.accounts.models import User

    owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)
    item = VaultItem.objects.create(
        user=owner, category="accounts", title="Secret", encrypted_password="do-not-leak"
    )
    client = logged_in(normal_user)

    assert client.get(f"{ITEMS}{item.id}/").status_code == 404
    assert client.patch(f"{ITEMS}{item.id}/", {"title": "hacked"}, format="json").status_code == 404
    assert client.delete(f"{ITEMS}{item.id}/").status_code == 404
    assert client.post(f"{ITEMS}{item.id}/reveal/", {"password": PASSWORD}, format="json").status_code == 404


def test_item_list_scoped_to_user(api, db, logged_in, normal_user):
    from apps.accounts.models import User

    other = User.objects.create_user(email="other@example.com", password=PASSWORD)
    VaultItem.objects.create(user=normal_user, category="notes", title="mine")
    VaultItem.objects.create(user=other, category="notes", title="theirs")

    client = logged_in(normal_user)
    response = client.get(ITEMS)
    assert response.data["count"] == 1
    assert response.data["results"][0]["title"] == "mine"


def test_search_matches_title_and_decrypted_fields(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    VaultItem.objects.create(user=normal_user, category="notes", title="Mars plans")
    VaultItem.objects.create(
        user=normal_user, category="accounts", title="Email", encrypted_username="neil@mars.gov"
    )

    assert client.get(f"{ITEMS}?search=mars").data["count"] == 2
    assert client.get(f"{ITEMS}?search=neil").data["count"] == 1


def test_file_upload_download_ownership(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    upload = SimpleUploadedFile("cert.pdf", b"%PDF-1.4 fake pdf content", content_type="application/pdf")
    response = client.post(FILES, {"file": upload}, format="multipart")
    assert response.status_code == 201
    file_id = response.data["id"]
    assert response.data["filename"] == "cert.pdf"

    # Owner can download the exact bytes.
    response = client.get(f"{FILES}{file_id}/download/")
    assert response.status_code == 200
    assert b"%PDF-1.4 fake pdf content" in response.content

    # Another user cannot see or download it.
    from apps.accounts.models import User

    other = User.objects.create_user(email="otherfile@example.com", password=PASSWORD)
    client2 = logged_in(other)
    assert client2.get(f"{FILES}{file_id}/").status_code == 404
    assert client2.get(f"{FILES}{file_id}/download/").status_code == 404


def test_file_linked_to_item_scoped(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    item = VaultItem.objects.create(user=normal_user, category="documents", title="Docs")
    upload = SimpleUploadedFile("image.png", b"\x89PNG\r\n\x1a\nfake", content_type="image/png")
    response = client.post(FILES, {"file": upload, "vault_item": item.id}, format="multipart")
    assert response.status_code == 201

    detail = client.get(f"{ITEMS}{item.id}/").data
    assert detail["file_count"] == 1


def test_file_upload_rejects_foreign_item(api, db, logged_in, normal_user):
    from apps.accounts.models import User

    owner = User.objects.create_user(email="owner2@example.com", password=PASSWORD)
    item = VaultItem.objects.create(user=owner, category="notes", title="theirs")
    client = logged_in(normal_user)
    upload = SimpleUploadedFile("leak.txt", b"payload", content_type="text/plain")
    response = client.post(FILES, {"file": upload, "vault_item": item.id}, format="multipart")
    assert response.status_code == 403


def test_blob_encrypted_on_disk(api, db, logged_in, normal_user, settings):
    client = logged_in(normal_user)
    upload = SimpleUploadedFile("secret.txt", b"TOP SECRET CONTENT", content_type="text/plain")
    response = client.post(FILES, {"file": upload}, format="multipart")
    file_obj = VaultFile.objects.get(id=response.data["id"])

    import os

    path = os.path.join(settings.PRIVATE_MEDIA_ROOT, file_obj.storage_key[:2], file_obj.storage_key)
    with open(path, "rb") as fh:
        on_disk = fh.read()
    assert b"TOP SECRET CONTENT" not in on_disk
    assert b"$" in on_disk  # envelope format


def test_delete_item_removes_files(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    item = VaultItem.objects.create(user=normal_user, category="notes", title="With files")
    upload = SimpleUploadedFile("doc.txt", b"abc", content_type="text/plain")
    client.post(FILES, {"file": upload, "vault_item": item.id}, format="multipart")

    assert client.delete(f"{ITEMS}{item.id}/").status_code == 204
    assert VaultFile.objects.count() == 0