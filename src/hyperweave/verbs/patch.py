"""RFC 6902 JSON Patch (subset) — the universal mutation mechanism for transform.

Any frame's payload is JSON, so a structural patch sets/extends/deletes fields
with no per-frame op vocabulary. Operates on a deep copy — never mutates the
input. Schema validation happens AFTER the patch (the caller re-validates the
result against the frame model), so an invalid shape fails cleanly as
SPEC_INVALID rather than producing a broken artifact.
"""

from __future__ import annotations

import copy
from typing import Any

from hyperweave.core.errors import HwError, HwErrorCode


def _bad(msg: str) -> HwError:
    return HwError(HwErrorCode.SPEC_INVALID, msg)


def _split_pointer(pointer: str) -> list[str]:
    """Parse a JSON Pointer (RFC 6901) into unescaped tokens."""
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise _bad(f"JSON pointer must start with '/': {pointer!r}")
    return [tok.replace("~1", "/").replace("~0", "~") for tok in pointer.split("/")[1:]]


def _index(arr: list[Any], token: str, *, allow_end: bool) -> int:
    if token == "-":
        return len(arr)
    try:
        idx = int(token)
    except ValueError:
        raise _bad(f"array index must be an integer or '-', got {token!r}") from None
    hi = len(arr) if allow_end else len(arr) - 1
    if idx < 0 or idx > hi:
        raise _bad(f"array index {idx} out of range (len {len(arr)})")
    return idx


def _descend(cur: Any, token: str) -> Any:
    if isinstance(cur, list):
        return cur[_index(cur, token, allow_end=False)]
    if isinstance(cur, dict):
        if token not in cur:
            raise _bad(f"path token {token!r} not found")
        return cur[token]
    raise _bad(f"cannot descend into {type(cur).__name__} at {token!r}")


def _get(doc: Any, pointer: str) -> Any:
    cur = doc
    for tok in _split_pointer(pointer):
        cur = _descend(cur, tok)
    return cur


def _parent(doc: Any, tokens: list[str]) -> Any:
    cur = doc
    for tok in tokens[:-1]:
        cur = _descend(cur, tok)
    return cur


def _set_or_insert(container: Any, key: str, value: Any, *, insert: bool) -> None:
    if isinstance(container, list):
        idx = _index(container, key, allow_end=True)
        if insert or idx == len(container):
            container.insert(idx, value)
        else:
            container[idx] = value
    elif isinstance(container, dict):
        container[key] = value
    else:
        raise _bad(f"cannot set {key!r} on {type(container).__name__}")


def _remove(container: Any, key: str) -> Any:
    if isinstance(container, list):
        idx = _index(container, key, allow_end=False)
        return container.pop(idx)
    if isinstance(container, dict):
        if key not in container:
            raise _bad(f"remove: key {key!r} not found")
        return container.pop(key)
    raise _bad(f"cannot remove {key!r} from {type(container).__name__}")


def apply_json_patch(doc: Any, ops: list[dict[str, Any]] | dict[str, Any]) -> Any:
    """Apply an RFC-6902 patch (or single op) to a deep copy of ``doc``."""
    op_list = [ops] if isinstance(ops, dict) else list(ops)
    result = copy.deepcopy(doc)
    for op in op_list:
        kind = op.get("op")
        path = str(op.get("path", ""))
        if kind in ("add", "replace"):
            if "value" not in op:
                raise _bad(f"{kind} op needs a 'value'")
            tokens = _split_pointer(path)
            if not tokens:
                result = op["value"]
                continue
            _set_or_insert(_parent(result, tokens), tokens[-1], op["value"], insert=(kind == "add"))
        elif kind == "remove":
            tokens = _split_pointer(path)
            if not tokens:
                raise _bad("cannot remove the document root")
            _remove(_parent(result, tokens), tokens[-1])
        elif kind in ("move", "copy"):
            frm = str(op.get("from", ""))
            value = copy.deepcopy(_get(result, frm))
            if kind == "move":
                ftokens = _split_pointer(frm)
                _remove(_parent(result, ftokens), ftokens[-1])
            tokens = _split_pointer(path)
            _set_or_insert(_parent(result, tokens), tokens[-1], value, insert=True)
        elif kind == "test":
            if _get(result, path) != op.get("value"):
                raise _bad(f"test op failed at {path!r}")
        else:
            raise _bad(f"unknown patch op {kind!r} (add|remove|replace|move|copy|test)")
    return result
