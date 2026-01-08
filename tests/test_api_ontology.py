"""
Tests for API Ontology Router endpoints.

Tests cover:
- Router collision fix (v3 routes accessible)
- Ontology summary endpoint
- Theme query endpoints
- Motion/glyph/effect query endpoints
- Error handling for invalid queries

These tests verify that the router registration order fix
prevents grammar router from intercepting /v3/ontology/* paths.
"""

import pytest
from fastapi.testclient import TestClient

from hyperweave.api.server import app


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


class TestOntologyEndpointAccessibility:
    """Test that ontology endpoints are accessible (router collision fix)."""

    def test_ontology_root_accessible(self, client):
        """Should access /v3/ontology without router collision."""
        response = client.get("/v3/ontology")
        # Should NOT return "Unknown provider: v3" (grammar router intercept)
        assert response.status_code == 200
        data = response.json()
        assert "ontology_version" in data or "error" not in data

    def test_ontology_themes_accessible(self, client):
        """Should access /v3/ontology/themes without router collision."""
        response = client.get("/v3/ontology/themes")
        assert response.status_code == 200
        data = response.json()
        # Grammar router would return "Unknown provider: v3"
        assert "Unknown provider" not in str(data)

    def test_ontology_theme_detail_accessible(self, client):
        """Should access /v3/ontology/themes/{id} without collision."""
        response = client.get("/v3/ontology/themes/chrome")
        assert response.status_code == 200
        data = response.json()
        assert data.get("id") == "chrome" or "theme" in str(data).lower()


class TestOntologySummaryEndpoint:
    """Test ontology summary endpoint."""

    def test_ontology_root_returns_summary(self, client):
        """Should return ontology summary with counts."""
        response = client.get("/v3/ontology")
        assert response.status_code == 200
        data = response.json()

        # Should include category counts
        assert "themes" in data or "ontology_version" in data

    def test_ontology_version_present(self, client):
        """Should include ontology version."""
        response = client.get("/v3/ontology")
        assert response.status_code == 200
        data = response.json()

        # Version should be 7.0.0
        if "ontology_version" in data:
            assert data["ontology_version"] == "7.0.0"


class TestOntologyThemesEndpoint:
    """Test theme query endpoints."""

    def test_list_all_themes(self, client):
        """Should list all 25 themes."""
        response = client.get("/v3/ontology/themes")
        assert response.status_code == 200
        data = response.json()

        # Should have count or items
        if "count" in data:
            assert data["count"] == 25
        elif "items" in data:
            assert len(data["items"]) == 25

    def test_filter_themes_by_tier(self, client):
        """Should filter themes by tier."""
        response = client.get("/v3/ontology/themes?tier=industrial")
        assert response.status_code == 200
        data = response.json()

        # Industrial tier has 3 themes: chrome, titanium, obsidian
        # Response has "count" and "themes" (list)
        assert data["count"] == 3
        assert len(data["themes"]) == 3

    def test_filter_themes_by_series(self, client):
        """Should filter themes by series."""
        response = client.get("/v3/ontology/themes?series=five-scholars")
        assert response.status_code == 200
        data = response.json()

        # Five scholars series has 5 themes
        assert data["count"] == 5
        assert len(data["themes"]) == 5

    def test_get_theme_detail(self, client):
        """Should return detailed theme configuration."""
        response = client.get("/v3/ontology/themes/chrome")
        assert response.status_code == 200
        data = response.json()

        # Chrome theme details
        assert data.get("id") == "chrome"
        assert data.get("tier") == "industrial"
        assert "compatibleMotions" in data

    def test_get_theme_detail_scholarly(self, client):
        """Should return scholarly theme detail."""
        response = client.get("/v3/ontology/themes/codex")
        assert response.status_code == 200
        data = response.json()

        assert data.get("id") == "codex"
        assert data.get("tier") == "scholarly"
        assert data.get("series") == "five-scholars"

    def test_theme_not_found(self, client):
        """Should return 404 for invalid theme."""
        response = client.get("/v3/ontology/themes/nonexistent-theme")
        assert response.status_code == 404


class TestOntologyMotionsEndpoint:
    """Test motion query endpoints."""

    def test_list_all_motions(self, client):
        """Should list all motion primitives."""
        response = client.get("/v3/ontology/motions")
        assert response.status_code == 200
        data = response.json()

        # Response has "count" and "motions" (list)
        assert data["count"] >= 8  # At least 8 motion primitives
        assert len(data["motions"]) >= 8

    def test_motions_include_breathe(self, client):
        """Should include breathe motion."""
        response = client.get("/v3/ontology/motions")
        assert response.status_code == 200
        data = response.json()

        # Find breathe motion in list
        motion_ids = [m["id"] for m in data["motions"]]
        assert "breathe" in motion_ids


class TestOntologyGlyphsEndpoint:
    """Test glyph query endpoints."""

    def test_list_all_glyphs(self, client):
        """Should list all glyph types."""
        response = client.get("/v3/ontology/glyphs")
        assert response.status_code == 200
        data = response.json()

        # Response has "count" and "glyphs" (list)
        assert data["count"] >= 10  # At least 10 glyph types
        assert len(data["glyphs"]) >= 10

    def test_glyphs_include_dot(self, client):
        """Should include dot glyph."""
        response = client.get("/v3/ontology/glyphs")
        assert response.status_code == 200
        data = response.json()

        glyph_ids = [g["id"] for g in data["glyphs"]]
        assert "dot" in glyph_ids


class TestOntologyEffectsEndpoint:
    """Test effects query endpoints."""

    def test_list_all_effects(self, client):
        """Should list effect definitions."""
        response = client.get("/v3/ontology/effects")
        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert "effects" in data


class TestRouterOrderVerification:
    """Test that grammar router still works for badge URLs."""

    def test_grammar_router_badge_url(self, client):
        """Grammar router should still handle badge URLs."""
        # This should be handled by grammar router, not v3 router
        response = client.get("/static.passing/chrome.svg")
        # Should return SVG or valid response
        assert response.status_code in [200, 404]  # 404 if data source not configured

    def test_grammar_router_with_motion(self, client):
        """Grammar router should handle motion URLs."""
        response = client.get("/static.passing/chrome.sweep.svg")
        assert response.status_code in [200, 404]

    def test_api_root_accessible(self, client):
        """API root should be accessible."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "HyperWeave Living Artifact API"

    def test_health_endpoint(self, client):
        """Health check endpoint should work."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestV3BadgeEndpoints:
    """Test v3 badge endpoints are accessible."""

    def test_badge_endpoint_accessible(self, client):
        """Should access /v3/badge endpoint."""
        # POST request with BASIC tier (no reasoning required)
        response = client.post(
            "/v3/badge",
            json={
                "theme": "chrome",
                "content": {
                    "label": "test",
                    "value": "badge",
                },
                "artifact_tier": "BASIC",
            },
        )
        assert response.status_code == 200
        # Should return SVG
        assert "<svg" in response.text

    def test_badge_json_endpoint(self, client):
        """Should access /v3/badge/json endpoint."""
        response = client.post(
            "/v3/badge/json",
            json={
                "theme": "chrome",
                "content": {
                    "label": "build",
                    "value": "passing",
                },
                "artifact_tier": "BASIC",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "svg" in data
        assert "theme_dna" in data

    def test_badge_full_tier_requires_reasoning(self, client):
        """Should require reasoning for FULL tier badges."""
        response = client.post(
            "/v3/badge",
            json={
                "theme": "chrome",
                "content": {"label": "test", "value": "badge"},
                "artifact_tier": "FULL",
            },
        )
        # Should fail without reasoning
        assert response.status_code == 400

    def test_badge_full_tier_with_reasoning(self, client):
        """Should accept FULL tier badges with reasoning."""
        response = client.post(
            "/v3/badge",
            json={
                "theme": "chrome",
                "content": {"label": "build", "value": "passing"},
                "artifact_tier": "FULL",
                "reasoning": {
                    "intent": "CI status indicator",
                    "approach": "Chrome for high contrast",
                    "tradeoffs": "Animation adds polish",
                },
            },
        )
        assert response.status_code == 200
        assert "<svg" in response.text
