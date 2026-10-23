"""Exercise the production API with synthetic providers in a temporary database.

Run inside the separate test API image. OAuth and publisher calls stay in process;
the real routes, storage, encrypted tokens and FFmpeg probe are exercised.
"""

import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlencode, urlparse


def run(root: Path) -> None:
    os.environ["CLIPPER_DATA_DIR"] = str(root)
    os.environ["CLIPPER_DATABASE_URL"] = f"sqlite:///{root / 'audit.db'}"

    from fastapi.testclient import TestClient

    import clipper.api.distribution as distribution_api
    import clipper.api.publications as publication_api
    import clipper.api.social_accounts as accounts_api
    from clipper.main import app
    from clipper.persistence import SessionLocal, create_schema
    from clipper.projects import PublishingConnectionService
    from clipper.providers.credentials import EncryptedCredentialStore
    from clipper.publishing import OAuthConnection, ProviderMetrics, PublishedPost

    create_schema()
    credentials = EncryptedCredentialStore(root)

    class OAuth:
        configured = True

        def __init__(self, platform: str) -> None:
            self.platform = platform

        def authorization_url(self, state: str) -> str:
            return "https://example.invalid/oauth?" + urlencode({"state": state})

        def exchange_code_candidates(
            self, code: str, state: str = ""
        ) -> list[OAuthConnection]:
            assert code == "synthetic-code" and state
            return [
                OAuthConnection(
                    access_token=f"synthetic-{self.platform}-{i}",
                    external_account_id=f"{self.platform}-{i}",
                    username=f"audit_{self.platform}_{i}",
                    display_name=f"Audit {self.platform} {i}",
                    parent_page_id="synthetic-page",
                    granted_scopes=()
                    if self.platform == "instagram" and i == 2
                    else (
                        "instagram_basic",
                        "instagram_content_publish",
                        "pages_read_engagement",
                        "https://www.googleapis.com/auth/youtube.force-ssl",
                    ),
                )
                for i in ([1, 2] if self.platform == "instagram" else [1])
            ]

        def exchange_code(self, code: str, state: str = "") -> OAuthConnection:
            return self.exchange_code_candidates(code, state)[0]

    calls: list[str] = []

    class Publisher:
        def publish(self, request, connection):
            calls.append(connection.external_account_id)
            external_id = "post-" + connection.external_account_id
            request.on_upload_started(external_id)
            return PublishedPost(
                post_url="https://example.invalid/" + external_id,
                external_id=external_id,
            )

        def refresh(self, *args):
            raise AssertionError("Completed uploads must not refresh")

        def metrics(self, external_id, post_url, connection):
            return ProviderMetrics(
                external_id=external_id, views=123, likes=4, comments=2
            )

        def update_post(self, external_id, post_url, title, description, connection):
            calls.append("update:" + external_id)

        def delete_post(self, external_id, post_url, connection):
            calls.append("delete:" + external_id)

    platforms = ("youtube", "instagram", "facebook", "tiktok", "x")
    accounts_api.publishing_connections = PublishingConnectionService(
        {platform: OAuth(platform) for platform in platforms},
        credentials,
    )
    publication_api.credential_store = credentials
    distribution_api.credential_store = credentials
    publication_api.publishing_adapters = {
        platform: Publisher() for platform in platforms
    }
    publication_api.metrics_adapters = publication_api.publishing_adapters

    def batch(queued):
        for publication_id, request in queued:
            with SessionLocal() as session:
                from clipper.persistence import Publication

                post = session.get(Publication, publication_id)
                publication_api.publication_service.publish_queued(
                    session,
                    publication_id,
                    request,
                    publication_api.publishing_adapters[post.platform],
                    credentials,
                )

    publication_api.run_publication_batch = batch
    distribution_api.run_publication_batch = batch
    # No lifespan workers: every background publish above uses a synthetic adapter.
    client = TestClient(app)

    def connect(platform: str, choice: str | None = None) -> dict:
        response = client.get(
            f"/api/social-accounts/connect/{platform}", follow_redirects=False
        )
        assert response.status_code == 307
        state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
        callback = client.get(
            f"/api/oauth/{platform}/callback",
            params={"state": state, "code": "synthetic-code"},
            follow_redirects=False,
        )
        assert callback.status_code == 303
        params = parse_qs(urlparse(callback.headers["location"]).query)
        if "connection_selection" in params:
            token = params["connection_selection"][0]
            pending = client.get("/api/social-account-selections/" + token)
            assert pending.status_code == 200
            assert "synthetic-" not in pending.text
            selection = client.post(
                "/api/social-account-selections/" + token,
                json={"external_account_id": choice or platform + "-1"},
            )
            assert selection.status_code == 200, selection.text
            assert (
                client.get("/api/social-account-selections/" + token).status_code == 409
            )
            return selection.json()
        assert "connected" in params, params
        return next(
            account
            for account in client.get("/api/social-accounts").json()
            if account["platform"] == platform
        )

    accounts = [connect(platform) for platform in platforms]
    restricted = connect("instagram", "instagram-2")
    assert len(client.get("/api/social-accounts").json()) == 6
    assert connect("youtube")["id"] == accounts[0]["id"]
    assert len(client.get("/api/social-accounts").json()) == 6
    assert (
        client.get(
            "/api/oauth/youtube/callback",
            params={"state": "invalid", "code": "synthetic-code"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    readiness = client.get("/api/social-accounts/readiness").json()
    assert sum(item["publishing_ready"] for item in readiness) == 5
    assert (
        "publishing_permission_missing"
        in next(item for item in readiness if item["account_id"] == restricted["id"])[
            "issues"
        ]
    )
    assert (
        client.put(
            "/api/social-accounts/" + accounts[0]["id"], json={"label": "  "}
        ).status_code
        == 422
    )

    media = root / "existing-video.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=navy:s=640x360:r=10:d=31",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-y",
            str(media),
        ],
        check=True,
    )
    upload = client.post(
        "/api/projects/upload-for-publishing",
        data={"title": "Publishing audit", "authorization_confirmed": "true"},
        files={"media": (media.name, media.read_bytes(), "video/mp4")},
    )
    assert upload.status_code == 201, upload.text
    project = upload.json()
    clip = project["clips"][0]
    group = client.post(
        "/api/social-account-groups",
        json={
            "name": "Audit group",
            "account_ids": [a["id"] for a in accounts] + [restricted["id"]],
        },
    ).json()
    result = client.post(
        f"/api/projects/{project['id']}/publish-batch",
        json={"clip_ids": [clip["id"]], "group_id": group["id"]},
    )
    assert result.status_code == 202, result.text
    assert result.json()["queued"] == 5 and len(result.json()["skipped"]) == 1
    assert len(calls) == 5 and len(set(calls)) == 5
    repeated = client.post(
        f"/api/projects/{project['id']}/publish-batch",
        json={"clip_ids": [clip["id"]], "group_id": group["id"]},
    )
    assert repeated.status_code == 202 and repeated.json()["queued"] == 0
    assert len(calls) == 5
    posts = client.get(f"/api/projects/{project['id']}").json()["clips"][0][
        "publications"
    ]
    youtube = next(post for post in posts if post["platform"] == "youtube")
    post_url = f"/api/publications/{youtube['id']}"
    assert (
        client.post(
            post_url + "/metrics", json={"views": 100, "revenue": 7}
        ).status_code
        == 200
    )
    assert client.post(post_url + "/metrics/sync").status_code == 200
    metrics = client.get(f"/api/projects/{project['id']}").json()["clips"][0][
        "publications"
    ]
    saved = next(post for post in metrics if post["id"] == youtube["id"])
    assert saved["metric_snapshots"][-1]["views"] == 123
    assert saved["metric_snapshots"][-1]["revenue"] == 7
    assert (
        client.put(
            post_url + "/remote",
            json={"title": "Updated title", "description": "Updated caption"},
        ).status_code
        == 200
    )
    assert (
        client.post(post_url + "/delete-remote", json={"confirm": False}).status_code
        == 422
    )
    assert (
        client.post(post_url + "/delete-remote", json={"confirm": True}).status_code
        == 200
    )
    assert client.post(post_url + "/refresh").status_code == 409
    history = client.get(post_url + "/management").json()["history"]
    assert {change["action"] for change in history} == {"update", "delete"}
    # Damaged credentials must not stop disconnection or removal.
    (root / "credentials" / (restricted["id"] + ".token")).write_text("damaged")
    assert (
        client.delete(f"/api/social-accounts/{restricted['id']}/connection").status_code
        == 200
    )
    assert credentials.load(restricted["id"]) is None
    assert client.delete(f"/api/social-accounts/{restricted['id']}").status_code == 204
    assert client.delete(post_url).status_code == 200
    assert client.delete(f"/api/social-account-groups/{group['id']}").status_code == 204
    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get("/api/projects").json() == []
    assert not (root / "projects" / project["id"]).exists()
    for account in accounts:
        assert client.delete(f"/api/social-accounts/{account['id']}").status_code == 204
        assert credentials.load(account["id"]) is None
    assert client.get("/api/social-accounts").json() == []
    print(
        json.dumps(
            {
                "status": "passed",
                "oauth_accounts": 6,
                "ready_destinations": 5,
                "synthetic_uploads": 5,
                "duplicate_uploads": 0,
                "remote_calls": 0,
                "verified": [
                    "OAuth discovery/replay rejection",
                    "readiness",
                    "group publishing with partial failure",
                    "duplicate prevention",
                    "metrics history",
                    "update/delete confirmation and history",
                    "corrupt-token disconnect",
                    "archive",
                    "cleanup",
                ],
            }
        )
    )


if __name__ == "__main__":
    with TemporaryDirectory(prefix="reachcut-social-audit-") as directory:
        run(Path(directory))
