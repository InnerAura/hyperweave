"""Leaf base model shared by every domain model.

Lives below ``core/models.py`` so sibling model modules (``core/matrix.py``)
can inherit ``FrozenModel`` without importing ``models.py`` — which itself
imports those siblings to nest them on ``ComposeSpec``. Import nothing from
hyperweave here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Base model with strict, frozen semantics.

    All domain models inherit from this instead of repeating ConfigDict.
    ``frozen=True`` makes instances immutable after creation.
    ``extra="forbid"`` rejects unknown fields at construction time.
    ``use_attribute_docstrings=True`` lets field docstrings serve as descriptions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", use_attribute_docstrings=True)
