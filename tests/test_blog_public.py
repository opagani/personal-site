"""All blog public-facing behavior is now exercised through the JSON API.
This file re-exports the API tests under their old names so a search for
'test_blog_public' still finds something. New tests should go in
tests/test_api.py."""

from tests.test_api import (  # noqa: F401 — re-exported for discovery
    test_api_blog_posts_lists_only_published as test_blog_list_published_only,
    test_api_blog_post_returns_body_html_and_only_approved_comments as test_blog_post_detail,
    test_api_blog_draft_404_for_anonymous as test_blog_draft_hidden,
    test_api_blog_draft_visible_to_signed_in_admin as test_blog_draft_visible_to_admin,
    test_api_comment_submission_happy_path as test_comment_submission_happy_path,
    test_api_comment_honeypot_silent_reject as test_honeypot_silent_reject,
    test_api_comment_fast_submit_silent_reject as test_fast_submit_silent_reject,
    test_api_comment_oversize_body_returns_422 as test_oversize_body_validation,
)
