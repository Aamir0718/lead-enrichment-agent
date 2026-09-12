"""Tests for the Processor Agent (agents/processor.py) -- pure, deterministic
functions with no network/browser dependency, so no mocking needed."""
from agents.processor import (
    MAX_TOTAL_CHARS,
    extract_emails,
    process_pages,
)


class TestExtractEmails:
    def test_finds_generic_prefixed_emails(self):
        text = "Reach us at contact@acme.com or sales@acme.com for a quote."
        found = extract_emails(text)
        assert found == {"contact@acme.com", "sales@acme.com"}

    def test_drops_non_generic_personal_emails(self):
        # The assignment spec asks for "generic or public emails
        # (contact@, sales@, support@)", not a named individual's address.
        text = "Contact Jane at jane.doe@acme.com for partnership inquiries."
        assert extract_emails(text) == set()

    def test_help_prefix_counts_as_generic(self):
        # help@ isn't in the assignment's example list but is clearly the
        # same category as contact@/support@ -- real postman.com data uses it.
        text = "Need something? Email help@postman.com any time."
        assert extract_emails(text) == {"help@postman.com"}

    def test_case_insensitive_and_deduplicated(self):
        text = "Contact@Acme.com works, and so does contact@acme.com."
        found = extract_emails(text)
        assert found == {"contact@acme.com"}

    def test_no_emails_in_text_returns_empty_set(self):
        assert extract_emails("This page has no email addresses at all.") == set()

    def test_rejects_overlong_junk_matches(self):
        # A pathological "email-shaped" string from minified JS/CSS leaking
        # through should not be reported.
        junk_local_part = "a" * 80
        text = f"info@{junk_local_part}.example.com"
        assert extract_emails(text) == set()


class TestProcessPages:
    def test_combines_multiple_pages_with_source_headers(self):
        pages = {
            "https://acme.com": "<html><body><p>Homepage text.</p></body></html>",
            "https://acme.com/about": "<html><body><p>About us text.</p></body></html>",
        }
        result = process_pages(pages)
        assert "--- Source: https://acme.com ---" in result.combined_text
        assert "--- Source: https://acme.com/about ---" in result.combined_text
        assert "Homepage text." in result.combined_text
        assert "About us text." in result.combined_text

    def test_strips_script_and_style_tags(self):
        pages = {
            "https://acme.com": (
                "<html><head><style>.x{color:red}</style></head>"
                "<body><script>alert('x')</script><p>Real content.</p></body></html>"
            )
        }
        result = process_pages(pages)
        assert "Real content." in result.combined_text
        assert "alert" not in result.combined_text
        assert "color:red" not in result.combined_text

    def test_combined_text_never_exceeds_max_total_chars(self):
        # One page with far more content than the cap allows.
        huge_body = "<p>" + ("word " * 20000) + "</p>"
        pages = {"https://acme.com": f"<html><body>{huge_body}</body></html>"}
        result = process_pages(pages)
        assert len(result.combined_text) <= MAX_TOTAL_CHARS

    def test_raw_emails_found_only_contains_generic_addresses(self):
        pages = {
            "https://acme.com": (
                "<html><body><p>Sales: sales@acme.com. "
                "Founder: jane.doe@acme.com.</p></body></html>"
            )
        }
        result = process_pages(pages)
        assert result.raw_emails_found == {"sales@acme.com"}

    def test_empty_pages_dict_produces_empty_result(self):
        result = process_pages({})
        assert result.combined_text == ""
        assert result.raw_emails_found == set()
