"""Animation stripping edits byte spans within syntactic scopes — never a
regex across the document.

Each fixture here is a failure class the previous pass set exhibited: an
unscoped ``animation:`` regex running past a closing quote, a lazy SMIL pair
bridging from a self-closing tag to an unrelated close, a whole-element match
swallowing kilobytes behind a self-closing shape, and edits landing inside
comments, CDATA payloads, CSS strings, or CSS comments. Byte preservation
outside edited spans is the standing law: BOM, newline style, quote style,
comments, payload, and envelope survive untouched.
"""

from __future__ import annotations

from hyperweave.formats.static import strip_animation, strip_animation_counted


class TestStyleAttributeScope:
    def test_semicolonless_final_declaration_does_not_detonate(self) -> None:
        # The recorded failure shape: the final declaration inside an attribute
        # carries no trailing semicolon; an unscoped regex ran past the closing
        # quote to the next ; or } anywhere in the document.
        svg = (
            '<svg><g style="animation:hw-ch1 18.7s linear infinite; animation-delay:0.058s">'
            "<rect/></g><text>after; still here</text></svg>"
        )
        out = strip_animation(svg)
        assert out == '<svg><g style=""><rect/></g><text>after; still here</text></svg>'

    def test_kept_declarations_are_byte_identical(self) -> None:
        svg = '<svg><g style="fill:#fff;  stroke-width:1.5 ;animation:a 1s;opacity:.9"><rect/></g></svg>'
        out = strip_animation(svg)
        assert 'style="fill:#fff;  stroke-width:1.5 ;opacity:.9"' in out

    def test_entities_and_quotes_inside_value_are_opaque(self) -> None:
        # &#59; is a semicolon entity — content, never a separator; &quot; is a
        # quote entity — never a string delimiter.
        svg = '<svg><text style="font-family:&quot;Inter&quot;;animation:a 1s;content:&#59;x">t</text></svg>'
        out = strip_animation(svg)
        assert 'style="font-family:&quot;Inter&quot;;content:&#59;x"' in out

    def test_url_with_semicolon_survives(self) -> None:
        svg = '<svg><g style="background:url(data:image/png;base64,AAAA);animation:a 1s"><rect/></g></svg>'
        out = strip_animation(svg)
        assert "url(data:image/png;base64,AAAA)" in out
        assert "animation:" not in out

    def test_single_quoted_attribute(self) -> None:
        svg = "<svg><g style='fill:red;animation:a 1s'><rect/></g></svg>"
        out = strip_animation(svg)
        assert "style='fill:red;'" in out or "style='fill:red'" in out


class TestStyleElementScope:
    def test_css_comment_and_string_content_untouched(self) -> None:
        svg = (
            "<svg><style>/* animation: not a declaration */"
            '.x{background:url("animation:fake.png");fill:red}</style><rect/></svg>'
        )
        assert strip_animation(svg) == svg

    def test_nested_media_keyframes_and_declarations(self) -> None:
        svg = (
            "<svg><style>"
            "@media (prefers-reduced-motion: reduce){.x{animation:none;opacity:1}}"
            "@media screen{@keyframes k{0%{opacity:0}100%{opacity:1}}}"
            ".y{fill:#123}"
            "</style></svg>"
        )
        out = strip_animation(svg)
        assert "@keyframes" not in out
        assert "animation:" not in out
        assert "@media (prefers-reduced-motion: reduce){.x{opacity:1}}" in out
        assert "@media screen{}" in out
        assert ".y{fill:#123}" in out

    def test_webkit_keyframes_removed(self) -> None:
        svg = "<svg><style>@-webkit-keyframes w{0%{opacity:0}}.x{fill:red}</style></svg>"
        out = strip_animation(svg)
        assert "keyframes" not in out
        assert ".x{fill:red}" in out

    def test_cdata_style_block_edited_inside_wrapper(self) -> None:
        svg = "<svg><style><![CDATA[.x{animation:a 1s;fill:red}@keyframes a{0%{opacity:0}}]]></style></svg>"
        out = strip_animation(svg)
        assert out == "<svg><style><![CDATA[.x{fill:red}]]></style></svg>"

    def test_animation_prefixed_properties_kept(self) -> None:
        # Properties that merely START with "animation" but are not animation-*
        # (custom props) and unrelated properties sharing the substring survive.
        svg = "<svg><style>.x{--animation-token:1;font:12px x}</style></svg>"
        assert strip_animation(svg) == svg


class TestSmilScanner:
    def test_mixed_self_closing_and_paired_forms(self) -> None:
        # The latent pair-regex failure: a self-closing instance must never
        # bridge to a later paired close tag.
        svg = (
            '<svg><path d="M0 0"><animateMotion dur="2.618s" path="M0 0 L9 9"/></path>'
            '<rect id="keep"/>'
            '<circle r="1"><animateMotion dur="1.618s"><mpath href="#p"/></animateMotion></circle></svg>'
        )
        out, counts = strip_animation_counted(svg)
        assert "<animate" not in out
        assert '<rect id="keep"/>' in out
        assert "<circle" in out
        assert counts["animated_elements_stripped"] == 2

    def test_gt_inside_attribute_value_does_not_end_tag(self) -> None:
        svg = '<svg><rect><animate values="0;1" to="a>b"/></rect></svg>'
        out = strip_animation(svg)
        assert "<animate" not in out
        assert "<rect></rect>" in out


class TestSelfClosingElementGuard:
    def test_self_closing_opacity_zero_shape_never_bridges(self) -> None:
        # The recorded 6,592-character over-match: a self-closing shape has no
        # body and no close tag of its own; the old pattern ran forward to an
        # unrelated close tag and deleted everything between.
        svg = (
            '<svg><circle opacity="0" r="2"/>'
            '<g id="payload-bearing"><text>real content</text>'
            '<circle r="3"><animate attributeName="opacity" values="0;1"/></circle></g></svg>'
        )
        out, counts = strip_animation_counted(svg)
        assert '<circle opacity="0" r="2"/>' in out  # static opacity-0: not animation-only
        assert "real content" in out
        assert "<animate" not in out
        assert counts.get("motion_only_elements_removed", 0) == 0


class TestProtectedSpans:
    def test_comments_cdata_bom_and_newlines_byte_preserved(self) -> None:
        # Nothing here is a live animation, so the strip is a byte-identity —
        # including the BOM, CRLF newlines, a comment carrying animation text,
        # and a CDATA payload carrying SMIL-shaped text.
        svg = (
            "﻿<svg>\r\n"
            "<!-- animation: 1s <animate/> not real -->\r\n"
            '<metadata><hw:payload xmlns:hw="x"><![CDATA['
            '{"style":"animation:a 1s","markup":"<animate attributeName=\\"o\\"/>"}'
            "]]></hw:payload></metadata>\r\n"
            "<rect/>\r\n</svg>"
        )
        assert strip_animation(svg) == svg

    def test_live_edits_leave_payload_untouched(self) -> None:
        payload = '<![CDATA[{"style":"animation:a 1s"}]]>'
        svg = (
            f'<svg><metadata><hw:payload xmlns:hw="x">{payload}</hw:payload></metadata>'
            '<g style="animation:a 1s"><rect/></g></svg>'
        )
        out = strip_animation(svg)
        assert payload in out
        assert 'style=""' in out


class TestVarFlattenScopes:
    """The variable flatten edits CSS and attribute values only — a label
    that literally reads ``var(--dna-signal)`` is content, and the payload's
    CDATA copy of it is evidence (review finding, 2026-08-30)."""

    def test_text_content_and_payload_survive_the_flatten(self) -> None:
        from hyperweave.formats.static import resolve_vars_to_hex

        svg = (
            "<svg><style>:root { --dna-signal: #1D4ED8; } .a { fill: var(--dna-signal); }</style>"
            '<metadata><hw:payload xmlns:hw="x"><![CDATA[{"label":"var(--dna-signal)"}]]></hw:payload></metadata>'
            '<text fill="var(--dna-signal)">shows var(--dna-signal) live</text>'
            '<rect fill="var(--dna-signal)"/></svg>'
        )
        out = resolve_vars_to_hex(svg)
        assert '<![CDATA[{"label":"var(--dna-signal)"}]]>' in out, "payload CDATA was edited"
        assert ">shows var(--dna-signal) live</text>" in out, "rendered text was edited"
        assert 'fill="#1D4ED8"' in out and "fill: #1D4ED8" in out, "real sinks must still resolve"
        assert '<text fill="#1D4ED8"' in out, "text-element ATTRIBUTES must still resolve"

    def test_static_projection_of_a_var_shaped_label_round_trips(self) -> None:
        from hyperweave.compose.engine import compose
        from hyperweave.core.models import ComposeSpec
        from hyperweave.formats import project

        spec = ComposeSpec(
            type="diagram",
            genome_id="primer",
            ground="opaque",
            palette="fixed",
            diagram={
                "topology": "pipeline",
                "nodes": [
                    {"id": "r", "label": "read", "desc": "uses var(--dna-signal)"},
                    {"id": "w", "label": "write"},
                ],
                "edges": [{"source": "r", "target": "w"}],
            },
        )
        data = project(compose(spec).svg, "svg-static").data
        text = data.decode() if isinstance(data, bytes) else data
        assert "var(--dna-signal)" in text, "the literal label text must survive the flatten"
        assert text.count("var(--dna-") >= 2, "label + payload copies both survive"

    def test_reasoning_metadata_survives_the_flatten(self) -> None:
        from hyperweave.formats.static import resolve_vars_to_hex

        svg = (
            "<svg><style>:root { --dna-signal: #1D4ED8; }</style>"
            '<metadata><hw:reasoning xmlns:hw="x"><hw:intent>bind var(--dna-signal) to the rail</hw:intent>'
            '</hw:reasoning></metadata><rect fill="var(--dna-signal)"/></svg>'
        )
        out = resolve_vars_to_hex(svg)
        assert "<hw:intent>bind var(--dna-signal) to the rail</hw:intent>" in out
        assert 'fill="#1D4ED8"' in out

    def test_dublin_core_provenance_survives_the_flatten(self) -> None:
        from hyperweave.formats.static import resolve_vars_to_hex

        svg = (
            "<svg><style>:root { --dna-signal: #1D4ED8; }</style>"
            '<metadata><rdf:RDF xmlns:rdf="r"><dc:title xmlns:dc="d">css: var(--dna-signal) demo</dc:title>'
            '</rdf:RDF></metadata><rect fill="var(--dna-signal)"/></svg>'
        )
        out = resolve_vars_to_hex(svg)
        assert "<dc:title" in out and "var(--dna-signal) demo</dc:title>" in out
        assert 'fill="#1D4ED8"' in out
