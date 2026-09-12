"""Tests for export.py's CSV flattening -- pure functions, no file I/O
needed except for write_csv's own round-trip test."""
import csv

from export import CSV_FIELDNAMES, _format_leadership, intel_to_csv_row, write_csv
from models import CompanyIntel, TeamMember


class TestFormatLeadership:
    def test_empty_list_is_empty_string(self):
        assert _format_leadership([]) == ""

    def test_includes_role_and_linkedin_when_present(self):
        member = TeamMember(name="Jane Doe", role="CEO", linkedin_url="https://linkedin.com/in/jane")
        assert _format_leadership([member]) == "Jane Doe (CEO) - https://linkedin.com/in/jane"

    def test_omits_missing_role_and_linkedin(self):
        member = TeamMember(name="Jane Doe")
        assert _format_leadership([member]) == "Jane Doe"

    def test_joins_multiple_members_with_semicolons(self):
        members = [TeamMember(name="Jane Doe", role="CEO"), TeamMember(name="John Roe", role="CTO")]
        assert _format_leadership(members) == "Jane Doe (CEO); John Roe (CTO)"


class TestIntelToCsvRow:
    def test_flattens_lists_and_drops_source_text(self):
        intel = CompanyIntel(
            domain="acme.com",
            status="success",
            company_overview="Acme builds widgets.",
            target_audience="Enterprises.",
            contact_emails=["contact@acme.com", "sales@acme.com"],
            leadership=[TeamMember(name="Jane Doe", role="CEO")],
            confidence_score=0.9,
            critique_notes=["note one"],
            pages_scraped=["https://acme.com", "https://acme.com/about"],
            source_text="a very long blob of scraped text" * 100,
        )
        row = intel_to_csv_row(intel)
        assert row["contact_emails"] == "contact@acme.com; sales@acme.com"
        assert row["leadership"] == "Jane Doe (CEO)"
        assert row["pages_scraped"] == "https://acme.com; https://acme.com/about"
        assert "source_text" not in row

    def test_none_error_becomes_empty_string(self):
        intel = CompanyIntel(domain="acme.com", status="success", error=None)
        assert intel_to_csv_row(intel)["error"] == ""


class TestWriteCsv:
    def test_writes_a_readable_csv_with_expected_rows(self, tmp_path):
        results = [
            CompanyIntel(domain="acme.com", status="success", company_overview="Acme."),
            CompanyIntel(domain="broke.com", status="failed", error="No pages could be fetched"),
        ]
        path = tmp_path / "output.csv"

        write_csv(results, path)

        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert [r["domain"] for r in rows] == ["acme.com", "broke.com"]
        assert rows[0]["status"] == "success"
        assert rows[1]["error"] == "No pages could be fetched"
        assert list(rows[0].keys()) == CSV_FIELDNAMES
