"""Action-specific permissions; publishing access never implies deletion access."""

from clipper.publishing.contracts import OAuthConnection


def instagram_deletion_issue(connection: OAuthConnection) -> str | None:
    if (
        "instagram_manage_contents" not in (connection.granted_scopes or ())
        or not connection.management_access_token
    ):
        return (
            "Instagram deletion is not authorized by this connection. "
            "In Meta Facebook Login for Business, add instagram_manage_contents to the "
            "ReachCut login configuration and allow a User access token, then reconnect "
            "this Instagram account. Publishing permission alone cannot delete media. "
            "You can open the original post in Instagram to delete it there."
        )
    return None


def instagram_publishing_issue(connection: OAuthConnection) -> str | None:
    if connection.granted_scopes is None:
        return None  # Legacy grants are checked against the linked Page before upload.
    required = {"instagram_basic", "instagram_content_publish", "pages_read_engagement"}
    missing = sorted(required - set(connection.granted_scopes))
    if missing:
        return (
            "Instagram publishing authorization is incomplete. Missing: "
            + ", ".join(missing)
            + ". Restore these permissions in the Meta login configuration, then reconnect "
            "the intended Instagram account and its linked Facebook Page in Accounts. "
            "Deletion permission does not replace publishing permission."
        )
    return None
