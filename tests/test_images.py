"""Images module tests.

Covers: upload validation (magic bytes, size), password-protected viewing,
ownership isolation (IDOR), rename, delete-with-blob-cleanup, search scoping,
unauthenticated access and admin isolation.
"""

from __future__ import annotations

import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.images.models import Image

from tests.conftest import PASSWORD

IMAGES = "/api/v1/images/"

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xd9" + b"\x00" * 32
)
WEBP_BYTES = b"RIFF\xf4\x02\x00\x00WEBPVP8L" + b"\x00" * 32
FAKE_BYTES = b"this is definitely not an image, just text pretending to be a png"


def _png(name="photo.png"):
    return SimpleUploadedFile(name, PNG_BYTES, content_type="image/png")


def _upload(api, *, file=None, name="", password="ImagePass123!", confirm=None):
    data = {
        "file": file or _png(),
        "password": password,
        "confirm_password": confirm if confirm is not None else password,
    }
    if name:
        data["name"] = name
    return api.post(IMAGES, data, format="multipart")


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def test_upload_png_jpeg_webp_ok(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    for file, ctype in [
        (_png(), "image/png"),
        (SimpleUploadedFile("a.jpg", JPEG_BYTES, content_type="image/jpeg"), "image/jpeg"),
        (SimpleUploadedFile("b.webp", WEBP_BYTES, content_type="image/webp"), "image/webp"),
    ]:
        response = _upload(client, file=file)
        assert response.status_code == 201, response.content
        assert response.data["content_type"] == ctype


def test_upload_stores_hash_not_plaintext_password(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = _upload(client, name="Passport 1")
    image = Image.objects.get(id=response.data["id"])
    assert "ImagePass123!" not in image.password_hash
    assert image.password_hash != ""
    # Random opaque storage key, never the original filename.
    assert image.storage_key != "photo.png"
    assert os.path.basename(image.storage_key) == image.storage_key


def test_upload_rejects_mime_spoofing(api, db, logged_in, normal_user):
    """Text bytes renamed to .png must be rejected server-side."""
    client = logged_in(normal_user)
    response = _upload(
        client,
        file=SimpleUploadedFile("evil.png", FAKE_BYTES, content_type="image/png"),
    )
    assert response.status_code == 400
    assert Image.objects.count() == 0


def test_upload_rejects_oversized_file(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    big = SimpleUploadedFile("big.png", PNG_BYTES + b"\x00" * (11 * 1024 * 1024), content_type="image/png")
    response = _upload(client, file=big)
    assert response.status_code == 400


def test_upload_requires_matching_confirmation(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    response = _upload(client, password="ImagePass123!", confirm="Different123!")
    assert response.status_code == 400


def test_upload_requires_authentication(api, db):
    from rest_framework.test import APIClient

    response = APIClient().post(IMAGES, {"file": _png(), "password": "x12345678"}, format="multipart")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Viewing / passwords
# ---------------------------------------------------------------------------

def test_view_with_wrong_and_correct_password(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    image_id = _upload(client).data["id"]

    wrong = client.post(f"{IMAGES}{image_id}/view/", {"password": "WrongPass123!"}, format="json")
    assert wrong.status_code == 403
    assert wrong.data["error"]["message"] == "Incorrect password."

    ok = client.post(f"{IMAGES}{image_id}/view/", {"password": "ImagePass123!"}, format="json")
    assert ok.status_code == 200
    assert ok["Content-Type"] == "image/png"
    assert ok.content == PNG_BYTES
    assert ok["Cache-Control"] == "no-store"


def test_view_never_returns_a_url(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    image_id = _upload(client).data["id"]
    detail = client.get(f"{IMAGES}{image_id}/").data
    serialized = str(detail)
    assert "url" not in serialized
    assert "storage_key" not in serialized
    assert "password_hash" not in serialized
    assert "/view/" not in serialized


def test_list_metadata_is_safe(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    _upload(client, name="secret-doc")
    listing = client.get(IMAGES).data["results"][0]
    assert set(listing.keys()) == {"id", "name", "content_type", "size", "created_at", "updated_at"}
    raw = Image.objects.get(id=listing["id"])
    assert raw.password_hash not in str(listing)


# ---------------------------------------------------------------------------
# Ownership isolation (IDOR)
# ---------------------------------------------------------------------------

def test_user_a_cannot_access_user_b_image(api, db, logged_in, normal_user):
    from apps.accounts.models import User
    from rest_framework.test import APIClient

    owner = User.objects.create_user(email="owner@example.com", password=PASSWORD)
    owner_client = APIClient()
    login_response = owner_client.post(
        "/api/v1/auth/login", {"email": owner.email, "password": PASSWORD}, format="json"
    )
    assert login_response.status_code == 200
    csrf = owner_client.cookies.get("myday_csrftoken")
    if csrf is not None:
        owner_client.defaults["HTTP_X_CSRFTOKEN"] = csrf.value
    image_id = _upload(owner_client).data["id"]

    attacker = logged_in(normal_user)
    assert attacker.get(f"{IMAGES}{image_id}/").status_code == 404
    assert attacker.patch(f"{IMAGES}{image_id}/", {"name": "hacked"}, format="json").status_code == 404
    assert attacker.delete(f"{IMAGES}{image_id}/").status_code == 404
    assert attacker.post(f"{IMAGES}{image_id}/view/", {"password": PASSWORD}, format="json").status_code == 404
    # Not listed either.
    ids = [item["id"] for item in attacker.get(IMAGES).data["results"]]
    assert image_id not in ids


def test_search_scoped_to_owner(api, db, logged_in, normal_user):
    from apps.accounts.models import User
    from rest_framework.test import APIClient

    other = User.objects.create_user(email="other@example.com", password=PASSWORD)
    other_client = APIClient()
    other_client.post("/api/v1/auth/login", {"email": other.email, "password": PASSWORD}, format="json")

    client = logged_in(normal_user)
    _upload(client, name="passport scan")

    mine = client.get(f"{IMAGES}?search=passport").data
    assert mine["count"] == 1
    assert mine["results"][0]["name"] == "passport scan"

    theirs = other_client.get(f"{IMAGES}?search=passport").data
    assert theirs["count"] == 0


# ---------------------------------------------------------------------------
# Rename & delete
# ---------------------------------------------------------------------------

def test_rename_updates_name_only(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    image_id = _upload(client, name="old-name").data["id"]
    response = client.patch(f"{IMAGES}{image_id}/", {"name": "new-name"}, format="json")
    assert response.status_code == 200
    assert response.data["name"] == "new-name"
    image = Image.objects.get(id=image_id)
    assert image.name == "new-name"


def test_rename_empty_name_rejected(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    image_id = _upload(client).data["id"]
    assert client.patch(f"{IMAGES}{image_id}/", {"name": "   "}, format="json").status_code == 400


def test_delete_removes_record_and_blob(api, db, logged_in, normal_user):
    from apps.core.storage import get_storage

    client = logged_in(normal_user)
    image_id = _upload(client).data["id"]
    storage_key = Image.objects.get(id=image_id).storage_key
    path = get_storage()._path(storage_key)
    assert os.path.exists(path)

    assert client.delete(f"{IMAGES}{image_id}/").status_code == 204
    assert Image.objects.count() == 0
    # No orphaned files left behind.
    assert not os.path.exists(path)


# ---------------------------------------------------------------------------
# Global search integration & admin isolation
# ---------------------------------------------------------------------------

def test_global_search_includes_images(api, db, logged_in, normal_user):
    client = logged_in(normal_user)
    _upload(client, name="passport")
    results = client.get("/api/v1/search?q=passport").data
    types = [group["type"] for group in results["groups"]]
    assert "image" in types


def test_admin_cannot_see_user_images_via_api(api, db, logged_in, normal_user, admin_user):
    client = logged_in(normal_user)
    image_id = _upload(client, name="private").data["id"]

    admin_client = logged_in(admin_user)
    assert admin_client.get(f"{IMAGES}{image_id}/").status_code == 404
    assert admin_client.get(f"{IMAGES}{image_id}/view/", {}).status_code == 405
    view = admin_client.post(f"{IMAGES}{image_id}/view/", {"password": PASSWORD}, format="json")
    assert view.status_code == 404
