import pytest
from io import BytesIO
from tests.conftest import auth_headers, make_user, TICKET_PAYLOAD


class TestUploadFile:
    def test_upload_file(self, client, db):
        user = make_user(db, telegram_id=1)
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user)).json()

        file_content = b"Test file content"
        r = client.post(
            f"/tickets/{ticket['id']}/files",
            files={"file": ("test.txt", BytesIO(file_content), "text/plain")},
            headers=auth_headers(user),
        )
        assert r.status_code == 201
        data = r.json()
        assert data["filename"] == "test.txt"
        assert data["filesize"] == len(file_content)
        assert "stored_path" in data

    def test_upload_forbidden_extension(self, client, db):
        user = make_user(db, telegram_id=1)
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user)).json()

        r = client.post(
            f"/tickets/{ticket['id']}/files",
            files={"file": ("malicious.exe", BytesIO(b"content"), "application/octet-stream")},
            headers=auth_headers(user),
        )
        assert r.status_code == 400
        assert "not allowed" in r.json()["detail"]

    def test_upload_too_large(self, client, db):
        user = make_user(db, telegram_id=1)
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user)).json()

        large_content = b"x" * (11 * 1024 * 1024)  # 11 MB
        r = client.post(
            f"/tickets/{ticket['id']}/files",
            files={"file": ("large.txt", BytesIO(large_content), "text/plain")},
            headers=auth_headers(user),
        )
        assert r.status_code == 400
        assert "too large" in r.json()["detail"]

    def test_upload_to_nonexistent_ticket(self, client, db):
        user = make_user(db, telegram_id=1)
        r = client.post(
            "/tickets/99999/files",
            files={"file": ("test.txt", BytesIO(b"content"), "text/plain")},
            headers=auth_headers(user),
        )
        assert r.status_code == 404

    def test_other_user_cannot_upload(self, client, db):
        owner = make_user(db, telegram_id=1)
        other = make_user(db, telegram_id=2)
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(owner)).json()

        r = client.post(
            f"/tickets/{ticket['id']}/files",
            files={"file": ("test.txt", BytesIO(b"content"), "text/plain")},
            headers=auth_headers(other),
        )
        assert r.status_code == 403

    def test_support_can_upload(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author)).json()

        r = client.post(
            f"/tickets/{ticket['id']}/files",
            files={"file": ("test.txt", BytesIO(b"content"), "text/plain")},
            headers=auth_headers(support),
        )
        assert r.status_code == 201

    def test_admin_can_upload(self, client, db):
        author = make_user(db, telegram_id=1)
        admin = make_user(db, telegram_id=2, role="admin")
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author)).json()

        r = client.post(
            f"/tickets/{ticket['id']}/files",
            files={"file": ("test.txt", BytesIO(b"content"), "text/plain")},
            headers=auth_headers(admin),
        )
        assert r.status_code == 201


class TestDownloadFile:
    def test_download_file(self, client, db, tmp_path):
        user = make_user(db, telegram_id=1)
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(user)).json()

        # Upload file first
        upload_r = client.post(
            f"/tickets/{ticket['id']}/files",
            files={"file": ("test.txt", BytesIO(b"Test content"), "text/plain")},
            headers=auth_headers(user),
        )
        stored_path = upload_r.json()["stored_path"]

        # Download file
        r = client.get(f"/files/{stored_path}", headers=auth_headers(user))
        assert r.status_code == 200
        assert r.content == b"Test content"

    def test_other_user_cannot_download(self, client, db):
        owner = make_user(db, telegram_id=1)
        other = make_user(db, telegram_id=2)
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(owner)).json()

        upload_r = client.post(
            f"/tickets/{ticket['id']}/files",
            files={"file": ("test.txt", BytesIO(b"content"), "text/plain")},
            headers=auth_headers(owner),
        )
        stored_path = upload_r.json()["stored_path"]

        r = client.get(f"/files/{stored_path}", headers=auth_headers(other))
        assert r.status_code == 403

    def test_download_nonexistent_file(self, client, db):
        user = make_user(db, telegram_id=1)
        r = client.get("/files/99999/nonexistent.txt", headers=auth_headers(user))
        assert r.status_code == 404

    def test_path_traversal_prevented(self, client, db):
        user = make_user(db, telegram_id=1)
        r = client.get("/files/../etc/passwd", headers=auth_headers(user))
        assert r.status_code == 403

    def test_support_can_download(self, client, db):
        author = make_user(db, telegram_id=1)
        support = make_user(db, telegram_id=2, role="support")
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author)).json()

        upload_r = client.post(
            f"/tickets/{ticket['id']}/files",
            files={"file": ("test.txt", BytesIO(b"content"), "text/plain")},
            headers=auth_headers(author),
        )
        stored_path = upload_r.json()["stored_path"]

        r = client.get(f"/files/{stored_path}", headers=auth_headers(support))
        assert r.status_code == 200

    def test_admin_can_download(self, client, db):
        author = make_user(db, telegram_id=1)
        admin = make_user(db, telegram_id=2, role="admin")
        ticket = client.post("/tickets", json=TICKET_PAYLOAD, headers=auth_headers(author)).json()

        upload_r = client.post(
            f"/tickets/{ticket['id']}/files",
            files={"file": ("test.txt", BytesIO(b"content"), "text/plain")},
            headers=auth_headers(author),
        )
        stored_path = upload_r.json()["stored_path"]

        r = client.get(f"/files/{stored_path}", headers=auth_headers(admin))
        assert r.status_code == 200