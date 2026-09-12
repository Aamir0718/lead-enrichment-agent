"""Tests for agents/scraper.py's pure helper functions -- URL normalization,
same-site checks, link ranking, and bot-block classification. No Playwright
browser is launched: `_rank_subpage_links` is exercised against a fake
`page` object that only implements the one method it actually calls."""
from agents.scraper import (
    MAX_SUBPAGES,
    _classify_possible_bot_block,
    _normalize_domain,
    _rank_subpage_links,
    _same_site,
)


class TestNormalizeDomain:
    def test_adds_https_scheme_when_missing(self):
        assert _normalize_domain("acme.com") == "https://acme.com"

    def test_keeps_existing_scheme(self):
        assert _normalize_domain("http://acme.com") == "http://acme.com"

    def test_strips_whitespace_and_trailing_slash(self):
        assert _normalize_domain("  acme.com/  ") == "https://acme.com"


class TestSameSite:
    def test_matches_identical_host(self):
        assert _same_site("https://acme.com", "https://acme.com/about") is True

    def test_ignores_www_prefix_on_either_side(self):
        assert _same_site("https://acme.com", "https://www.acme.com/team") is True
        assert _same_site("https://www.acme.com", "https://acme.com/team") is True

    def test_rejects_a_different_registrable_domain(self):
        assert _same_site("https://acme.com", "https://other.com/about") is False

    def test_rejects_an_unrelated_subdomain(self):
        # blog.acme.com is not the same host as acme.com -- only the exact
        # (www-normalized) host should count as same-site.
        assert _same_site("https://acme.com", "https://blog.acme.com/post") is False


class FakePage:
    """Minimal stand-in for a Playwright Page -- only implements the one
    method `_rank_subpage_links` actually calls."""

    def __init__(self, anchors):
        self._anchors = anchors

    def eval_on_selector_all(self, selector, script):
        return self._anchors


class TestRankSubpageLinks:
    def test_ranks_keyword_matches_above_generic_links(self):
        page = FakePage([
            {"href": "https://acme.com/about", "text": "About us"},
            {"href": "https://acme.com/blog", "text": "Blog"},
            {"href": "https://acme.com/team", "text": "Our team"},
        ])
        ranked = _rank_subpage_links(page, "https://acme.com")
        assert "https://acme.com/blog" not in ranked  # no keyword match, no score
        assert "https://acme.com/about" in ranked
        assert "https://acme.com/team" in ranked

    def test_filters_out_cross_site_links(self):
        page = FakePage([
            {"href": "https://other.com/about", "text": "About (external)"},
            {"href": "https://acme.com/contact", "text": "Contact"},
        ])
        ranked = _rank_subpage_links(page, "https://acme.com")
        assert ranked == ["https://acme.com/contact"]

    def test_caps_results_at_max_subpages(self):
        anchors = [
            {"href": f"https://acme.com/team{i}", "text": "team"} for i in range(MAX_SUBPAGES + 5)
        ]
        page = FakePage(anchors)
        ranked = _rank_subpage_links(page, "https://acme.com")
        assert len(ranked) == MAX_SUBPAGES

    def test_deduplicates_same_url_with_and_without_trailing_slash(self):
        page = FakePage([
            {"href": "https://acme.com/about/", "text": "About"},
            {"href": "https://acme.com/about", "text": "About us again"},
        ])
        ranked = _rank_subpage_links(page, "https://acme.com")
        assert ranked == ["https://acme.com/about"]

    def test_no_anchors_returns_empty_list(self):
        assert _rank_subpage_links(FakePage([]), "https://acme.com") == []


class FakeResponse:
    def __init__(self, status):
        self.status = status


class TestClassifyPossibleBotBlock:
    def test_flags_known_bot_block_status_codes(self):
        reason = _classify_possible_bot_block(FakeResponse(403), "<html>Some page</html>")
        assert reason is not None
        assert "403" in reason

    def test_flags_known_challenge_page_markers_even_on_200(self):
        html = "<html><title>Just a moment...</title>Checking your browser</html>"
        reason = _classify_possible_bot_block(FakeResponse(200), html)
        assert reason is not None
        assert "just a moment" in reason.lower()

    def test_returns_none_for_a_normal_page(self):
        reason = _classify_possible_bot_block(FakeResponse(200), "<html>Welcome to Acme</html>")
        assert reason is None

    def test_handles_a_missing_response_gracefully(self):
        # e.g. an in-page navigation, where Playwright returns None.
        assert _classify_possible_bot_block(None, "<html>Welcome to Acme</html>") is None
