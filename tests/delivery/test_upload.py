"""Upload seam — honest unavailability + the Protocol contract."""

from __future__ import annotations

import pytest

from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.delivery import upload


class _FakeUploader:
    name = "fake"

    def upload(self, data: bytes, *, media_type: str, filename: str) -> str:
        return f"https://host/{filename}"


@pytest.fixture(autouse=True)
def _clean_registry() -> object:
    """Each test starts with the shipped (empty) uploader registry."""
    saved = dict(upload._UPLOADERS)
    upload._UPLOADERS.clear()
    yield
    upload._UPLOADERS.clear()
    upload._UPLOADERS.update(saved)


def test_no_uploaders_is_honest_unavailable() -> None:
    """The shipped state: no uploader → FORMAT_UNAVAILABLE naming the seam."""
    with pytest.raises(HwError) as exc:
        upload.resolve_uploader()
    assert exc.value.code is HwErrorCode.FORMAT_UNAVAILABLE
    assert "url" in exc.value.fix


def test_single_registered_uploader_is_the_default() -> None:
    upload.register_uploader(_FakeUploader())
    assert upload.resolve_uploader().name == "fake"


def test_unknown_named_uploader_raises() -> None:
    upload.register_uploader(_FakeUploader())
    with pytest.raises(HwError) as exc:
        upload.resolve_uploader("missing")
    assert exc.value.code is HwErrorCode.FORMAT_UNAVAILABLE


def test_uploader_protocol_is_runtime_checkable() -> None:
    assert isinstance(_FakeUploader(), upload.Uploader)
