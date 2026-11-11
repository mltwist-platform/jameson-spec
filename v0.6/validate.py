#!/usr/bin/env python3
"""
Reference validator for JAMESON v0.6 documents (spec: README.md beside this file).

Usage:
    python3 validate.py FILE.json [FILE.json ...]
    python3 validate.py --self-test     # examples/ plus every case in tests/manifest.json

Checks every rule in §16 plus the value shapes, constraints, and ontology
well-formedness rules they reference (§7–§14). Exit status: 0 when every file is
valid, 1 when any file has errors, 2 when a file cannot be read or parsed.
Warnings (SHOULD-level guidance) never fail a file unless --strict is given.

This validator checks v0.6 only. A document whose jameson_version is not "0.6"
is rejected with a pointer to the validator in that version's folder.

Standard library only. Two checks are exact only with optional packages:
  - `json_schema` constraints (§8.3, §8.6) are checked and applied with
    `jsonschema` when installed; otherwise only the no-remote-$ref rule runs.
  - `pattern` constraints (§8.6) are compiled with `google-re2` when installed;
    otherwise the safe subset is checked by rejecting backreferences and
    lookaround, and patterns are compiled and matched with Python's `re`.

Interpretations where the spec is silent (stated here so they are visible):
  - `required` (§10.2, §16 rule 8): the spec does not scope fields to part
    types, yet its own examples answer different fields on different kinds of
    parts (e.g. `transcript` on audio segments, never on the file part). So when
    a document answers more than one kind of part, a required field is enforced
    on a part type only if some annotation on that part type answers the field.
    When only one kind of part is answered, every required field applies to it.
  - `pattern` matches anywhere in the value (unanchored), as in JSON Schema.
  - `info` is expected (§3 lists it) but its absence is a warning, not an error.
"""

import argparse
import ipaddress
import json
import math
import re
import sys
import uuid as uuidlib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

VERSION = "0.6"

FORM_TYPES = {
    "boolean", "text", "number", "single_select", "multi_select",
    "cascading_select", "date", "url", "json",
}
GEOMETRY_TYPES = {
    "bbox", "rotated_bbox", "polygon", "polyline", "point", "keypoints", "mask", "bbox3d",
}
FIELD_TYPES = FORM_TYPES | GEOMETRY_TYPES

PART_TYPES = {"file", "mesh", "row", "frame", "track", "segment", "region", "page", "span"}

# §7: required / optional locator keys per part type (None = locator must be omitted).
LOCATORS = {
    "file": None,
    "track": None,
    "region": None,
    "mesh": ({"node_path"}, {"mesh_index"}),
    "row": ({"row_index"}, {"sheet"}),
    "frame": ({"frame_index"}, {"timestamp"}),
    "page": ({"page_index"}, set()),
    "span": ({"start_char", "end_char"}, set()),
    "segment": (set(), {"start_time", "end_time", "start_frame", "end_frame"}),
}

# §8.3: legal constraint keys per field type.
CONSTRAINT_KEYS = {
    "number": {"min", "max", "exclusive_min", "exclusive_max", "step", "integer"},
    "text": {"min_length", "max_length", "format", "pattern"},
    "url": {"min_length", "max_length", "pattern"},
    "multi_select": {"min_items", "max_items"},
    "json": {"json_schema"},
    "date": {"min_date", "max_date"},
    "polygon": {"min_points", "max_points"},
    "polyline": {"min_points", "max_points"},
}

FORMATS = {"email", "phone_e164", "uuid", "hostname", "ipv4", "ipv6"}

# §8.5: registered render hints per type.
RENDER_HINTS = {
    "single_select": {"dropdown", "radio"},
    "multi_select": {"checklist", "dropdown", "tags"},
    "boolean": {"checkbox", "toggle"},
    "text": {"input", "textarea"},
    "number": {"input", "slider"},
    "date": {"date_picker"},
}

# §10: operators and the trigger field types each accepts (None = any type).
OPERATORS = {
    "equals": {"single_select", "text", "url", "date"},
    "in": {"single_select", "text", "url", "date"},
    "contains_any": {"multi_select", "cascading_select"},
    "is_true": {"boolean"},
    "is_false": {"boolean"},
    "is_answered": None,
}
OPERATORS_WITH_VALUES = {"equals", "in", "contains_any"}

KEYPOINT_VISIBILITY = {"visible", "occluded", "absent"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$"
)
_EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
_E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
# §8.6 safe subset: no backreferences, no lookahead / lookbehind (RE2-compatible).
_UNSAFE_PATTERN_RE = re.compile(r"\\[1-9]|\\k<|\(\?P=|\(\?=|\(\?!|\(\?<=|\(\?<!|\(\?\(")

try:  # optional: exact RE2 semantics
    import re2 as _re2  # type: ignore
except ImportError:  # pragma: no cover - depends on environment
    _re2 = None
try:  # optional: JSON Schema draft 2020-12
    import jsonschema as _jsonschema  # type: ignore
except ImportError:  # pragma: no cover - depends on environment
    _jsonschema = None


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_num(v):
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and not (isinstance(v, float) and not math.isfinite(v)))


def is_pos_int(v):
    return is_int(v) and v > 0


def is_whole(v):
    return is_num(v) and float(v).is_integer()


def is_iso_date(v):
    if not isinstance(v, str) or not _DATE_RE.match(v):
        return False
    try:
        date.fromisoformat(v)
        return True
    except ValueError:
        return False


def is_iso_datetime(v):
    if not isinstance(v, str) or not _DATETIME_RE.match(v):
        return False
    s = v.replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    m = re.search(r"([+-]\d{2})(\d{2})$", s)
    if m and ":" not in s[-6:]:
        s = s[: m.start()] + m.group(1) + ":" + m.group(2)
    try:
        datetime.fromisoformat(s)
        return True
    except ValueError:
        return False


def ref(v):
    """A dict/set key for a reference value; malformed (unhashable) values get a key that matches nothing."""
    return v if isinstance(v, (str, int, float, bool, type(None))) else ("<malformed>", id(v))


def is_x(name):
    return isinstance(name, str) and name.startswith("x-")


def dec(v):
    return Decimal(repr(v)) if isinstance(v, float) else Decimal(v)


def split_node_path(path):
    """Split a §7 node_path on unescaped '/'; returns the raw (still escaped) elements."""
    out, cur, i = [], "", 0
    while i < len(path):
        ch = path[i]
        if ch == "\\" and i + 1 < len(path):
            cur += path[i: i + 2]
            i += 2
            continue
        if ch == "/":
            out.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    out.append(cur)
    return out


def node_path_error(path):
    """Return a description of what is wrong with a node_path, or None."""
    if not path:
        return "is empty"
    elements = split_node_path(path)
    for el in elements:
        if el == "":
            return "has an empty path element"
    for el in elements[1:]:
        m = re.match(r"^(.*)\[(\d+)\]$", el, re.S)
        if not m or m.group(1).endswith("\\"):
            return f"element {el!r} lacks a [n] child index (required on every element but the root)"
        if re.search(r"(?<!\\)[\[\]]", m.group(1)):
            return f"element {el!r} has an unescaped '[' or ']' in its name"
    if re.search(r"(?<!\\)[\[\]]", elements[0]):
        return f"root element {elements[0]!r} has an unescaped '[' or ']' (the root carries no index)"
    return None


class Report:
    """Collects findings. Every error cites the spec: messages without a § reference
    get the citation of the section being checked (``section``)."""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.section = None

    def _cite(self, msg):
        return msg if "§" in msg or not self.section else f"{msg} ({self.section})"

    def error(self, where, msg):
        self.errors.append(f"{where}: {self._cite(msg)}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {self._cite(msg)}")


# ---------------------------------------------------------------------------
# Pattern + format checks
# ---------------------------------------------------------------------------

def compile_pattern(pattern):
    """Compile a §8.6 pattern; returns (compiled, error)."""
    if _re2 is not None:
        try:
            return _re2.compile(pattern), None
        except Exception as exc:  # noqa: BLE001 - re2 raises its own error types
            return None, f"does not compile as RE2: {exc}"
    if _UNSAFE_PATTERN_RE.search(pattern):
        return None, "uses backreferences, lookaround, or conditionals (outside the linear-time safe subset)"
    try:
        return re.compile(pattern), None
    except re.error as exc:
        return None, f"does not compile: {exc}"


def format_ok(fmt, value):
    if fmt == "email":
        return bool(_EMAIL_RE.match(value))
    if fmt == "phone_e164":
        return bool(_E164_RE.match(value))
    if fmt == "uuid":
        if not _UUID_RE.match(value):
            return False
        try:
            uuidlib.UUID(value)
            return True
        except ValueError:
            return False
    if fmt == "hostname":
        if len(value) > 253 or not value:
            return False
        labels = value[:-1].split(".") if value.endswith(".") else value.split(".")
        return all(_HOST_LABEL_RE.match(label) for label in labels)
    if fmt == "ipv4":
        try:
            ipaddress.IPv4Address(value)
            return True
        except ValueError:
            return False
    if fmt == "ipv6":
        try:
            ipaddress.IPv6Address(value)
            return True
        except ValueError:
            return False
    return True  # x- formats are unvalidated


def remote_refs(schema):
    """Yield every $ref in a JSON Schema that does not point inside the document."""
    if isinstance(schema, dict):
        for k, v in schema.items():
            if k == "$ref" and isinstance(v, str) and not v.startswith("#"):
                yield v
            else:
                yield from remote_refs(v)
    elif isinstance(schema, list):
        for item in schema:
            yield from remote_refs(item)


# ---------------------------------------------------------------------------
# Ontology (§8, §9, §10, §13)
# ---------------------------------------------------------------------------

def taxonomy_depths(nodes, rep, where, depth=1):
    """Validate a taxonomy tree; returns the set of depths at which branches end."""
    ends = set()
    if not isinstance(nodes, list) or not nodes:
        rep.error(where, "taxonomy level must be a non-empty array of nodes")
        return ends
    seen = set()
    for i, node in enumerate(nodes):
        w = f"{where}[{i}]"
        if not isinstance(node, dict):
            rep.error(w, "taxonomy node must be an object")
            continue
        if not isinstance(node.get("value"), str):
            rep.error(w, "taxonomy node needs a string 'value'")
        elif node["value"] in seen:
            rep.error(w, f"duplicate taxonomy value {node['value']!r} among siblings (§16 rule 2)")
        else:
            seen.add(node["value"])
        if not isinstance(node.get("label"), str):
            rep.error(w, "taxonomy node needs a string 'label'")
        children = node.get("children")
        if children is None or children == []:
            ends.add(depth)
        else:
            ends |= taxonomy_depths(children, rep, f"{w}.children", depth + 1)
    return ends


def check_constraints(field, rep, where):
    ftype = field.get("type")
    c = field.get("constraints")
    if c is None or not isinstance(ftype, str):
        return
    if not isinstance(c, dict):
        rep.error(where, "constraints must be an object")
        return
    legal = CONSTRAINT_KEYS.get(ftype, set())
    for key in c:
        if key not in legal:
            rep.error(where, f"constraint {key!r} is not legal for type {ftype!r} (§8.3)")

    def num(key):
        v = c.get(key)
        if key in c and not is_num(v):
            rep.error(where, f"constraint {key!r} must be a number")
            return None
        return v

    if ftype == "number":
        lo, hi = num("min"), num("max")
        xlo, xhi = num("exclusive_min"), num("exclusive_max")
        step = num("step")
        integer = c.get("integer")
        if "integer" in c and not isinstance(integer, bool):
            rep.error(where, "constraint 'integer' must be a boolean")
        if "min" in c and "exclusive_min" in c:
            rep.error(where, "'min' and 'exclusive_min' must not both be present (§8.3)")
        if "max" in c and "exclusive_max" in c:
            rep.error(where, "'max' and 'exclusive_max' must not both be present (§8.3)")
        low = lo if lo is not None else xlo
        high = hi if hi is not None else xhi
        if low is not None and high is not None:
            strict = xlo is not None or xhi is not None
            if low > high or (strict and low >= high):
                rep.error(where, "number bounds admit no value (§8.6)")
        if step is not None and step <= 0:
            rep.error(where, "'step' must be > 0 (§8.6)")
        if integer is True:
            for key in ("min", "max", "exclusive_min", "exclusive_max", "step"):
                if key in c and is_num(c[key]) and not is_whole(c[key]):
                    rep.error(where, f"integer: true requires a whole-number {key!r} (§8.3.2)")
            if low is not None and high is not None:
                first = math.floor(low) + 1 if xlo is not None else math.ceil(low)
                last = math.ceil(high) - 1 if xhi is not None else math.floor(high)
                if first > last:
                    rep.error(where, "integer: true with bounds that contain no whole number (§8.6)")

    for a, b in (("min_length", "max_length"), ("min_items", "max_items"), ("min_points", "max_points")):
        for key in (a, b):
            if key in c and not (is_int(c[key]) and c[key] >= 0):
                rep.error(where, f"constraint {key!r} must be a non-negative integer")
        if is_int(c.get(a)) and is_int(c.get(b)) and c[a] > c[b]:
            rep.error(where, f"{a} > {b} admits no value (§8.6)")
    if ftype == "multi_select" and is_int(c.get("max_items")):
        if c["max_items"] > len(_list(field.get("options"))):
            rep.error(where, "max_items exceeds the number of options (§8.6)")
    if ftype == "polygon" and is_int(c.get("max_points")) and c["max_points"] < 3:
        rep.error(where, "polygon max_points below 3 admits no value (§8.3)")

    if "format" in c:
        fmt = c["format"]
        if not isinstance(fmt, str):
            rep.error(where, "constraint 'format' must be a string")
        elif fmt not in FORMATS:
            if is_x(fmt):
                rep.warn(where, f"format {fmt!r} is unregistered; values are not validated against it (§8.3.1)")
            else:
                rep.error(where, f"format {fmt!r} is not registered and not x- prefixed (§8.3.1)")
    if "pattern" in c:
        if not isinstance(c["pattern"], str):
            rep.error(where, "constraint 'pattern' must be a string")
        else:
            _compiled, err = compile_pattern(c["pattern"])
            if err:
                rep.error(where, f"pattern {err} (§8.6)")
    if "json_schema" in c:
        schema = c["json_schema"]
        if not isinstance(schema, (dict, bool)):
            rep.error(where, "json_schema must be a JSON Schema object (§8.6)")
        else:
            for ref in remote_refs(schema):
                rep.error(where, f"json_schema uses remote $ref {ref!r}; schemas must be self-contained (§8.6)")
            if _jsonschema is not None:
                try:
                    _jsonschema.Draft202012Validator.check_schema(schema)
                except Exception as exc:  # noqa: BLE001
                    rep.error(where, f"json_schema is not a valid draft 2020-12 schema: {exc.__class__.__name__}")
    for key in ("min_date", "max_date"):
        if key in c and not is_iso_date(c[key]):
            rep.error(where, f"{key} {c[key]!r} is not an ISO 8601 date (§8.6)")
    if is_iso_date(c.get("min_date")) and is_iso_date(c.get("max_date")) and c["min_date"] > c["max_date"]:
        rep.error(where, "min_date > max_date admits no value (§8.6)")


def check_fields(doc, rep):
    rep.section = "§8"
    fields = doc.get("fields")
    by_name, index_of = {}, {}
    if not isinstance(fields, list):
        return by_name
    ids = set()
    for i, f in enumerate(fields):
        where = f"fields[{i}]"
        if not isinstance(f, dict):
            rep.error(where, "field must be an object")
            continue
        fid, name, ftype = f.get("id"), f.get("name"), f.get("type")
        if not is_pos_int(fid):
            rep.error(where, "'id' must be a positive integer")
        elif fid in ids:
            rep.error(where, f"duplicate field id {fid} (§16 rule 2)")
        else:
            ids.add(fid)
        if not isinstance(name, str) or not name:
            rep.error(where, "'name' must be a non-empty string")
        elif name in by_name:
            rep.error(where, f"duplicate field name {name!r} (§16 rule 2)")
        else:
            by_name[name] = f
            index_of[name] = i
        if not isinstance(ftype, str):
            rep.error(where, "'type' must be a string")
            continue
        if ftype not in FIELD_TYPES and not is_x(ftype):
            rep.error(where, f"type {ftype!r} is not registered and not x- prefixed (§9.6)")
            continue
        for key in ("label", "description"):
            if key in f and f[key] is not None and not isinstance(f[key], str):
                rep.error(where, f"{key!r} must be a string")
        if "required" in f and not isinstance(f["required"], bool):
            rep.error(where, "'required' must be a boolean")
        if "extra" in f and f["extra"] is not None and not isinstance(f["extra"], dict):
            rep.error(where, "'extra' must be an object")

        # options (§8.1)
        if ftype in ("single_select", "multi_select"):
            opts = f.get("options")
            if not isinstance(opts, list) or not opts:
                rep.error(where, f"{ftype} requires a non-empty 'options' array (§8)")
            else:
                seen = set()
                for j, o in enumerate(opts):
                    w = f"{where}.options[{j}]"
                    if not isinstance(o, dict):
                        rep.error(w, "options must be objects, never bare strings (§8.1)")
                        continue
                    if not isinstance(o.get("value"), str):
                        rep.error(w, "option needs a string 'value'")
                    elif o["value"] in seen:
                        rep.error(w, f"duplicate option value {o['value']!r} (§16 rule 2)")
                    else:
                        seen.add(o["value"])
                    if not isinstance(o.get("label"), str):
                        rep.error(w, "option needs a string 'label'")
        elif "options" in f:
            rep.error(where, f"'options' is forbidden on type {ftype!r} (§8)")

        # cascading (§8.2)
        if ftype == "cascading_select":
            levels = f.get("levels")
            if not isinstance(levels, list) or len(levels) < 2:
                rep.error(where, "cascading_select requires 'levels' with at least 2 entries (§8.2)")
                levels = levels if isinstance(levels, list) else []
            for j, lv in enumerate(levels):
                if not isinstance(lv, dict) or not isinstance(lv.get("label"), str):
                    rep.error(f"{where}.levels[{j}]", "level must be an object with a string 'label'")
            rfp = f.get("require_full_path", True)
            if not isinstance(rfp, bool):
                rep.error(where, "'require_full_path' must be a boolean")
            rep.section = "§8.2"
            ends = taxonomy_depths(f.get("taxonomy"), rep, f"{where}.taxonomy")
            rep.section = "§8"
            if levels and ends:
                if max(ends) > len(levels):
                    rep.error(where, "taxonomy is deeper than its levels (§8.2)")
                if rfp is True and min(ends) < len(levels):
                    rep.error(where, "require_full_path: true but a taxonomy branch ends before the last level (§8.2)")
        else:
            for key in ("levels", "taxonomy", "require_full_path"):
                if key in f:
                    rep.error(where, f"{key!r} is only legal on cascading_select (§8)")

        # keypoints (§9.4)
        if ftype == "keypoints":
            points = f.get("points")
            names = set()
            if not isinstance(points, list) or not points:
                rep.error(where, "keypoints requires a non-empty 'points' roster (§9.4)")
            else:
                for j, p in enumerate(points):
                    if not isinstance(p, dict) or not isinstance(p.get("name"), str):
                        rep.error(f"{where}.points[{j}]", "landmark needs a string 'name'")
                    elif p["name"] in names:
                        rep.error(f"{where}.points[{j}]", f"duplicate landmark name {p['name']!r} (§16 rule 2)")
                    else:
                        names.add(p["name"])
            skel = f.get("skeleton")
            if skel is not None:
                if not isinstance(skel, list):
                    rep.error(where, "'skeleton' must be an array of [nameA, nameB] pairs")
                else:
                    for j, pair in enumerate(skel):
                        if (not isinstance(pair, list) or len(pair) != 2
                                or not all(isinstance(n, str) and n in names for n in pair)):
                            rep.error(f"{where}.skeleton[{j}]", "pair must reference two rostered landmark names (§9.4)")
        else:
            for key in ("points", "skeleton"):
                if key in f:
                    rep.error(where, f"{key!r} is only legal on keypoints (§8)")

        # render (§8.5)
        if "render" in f and f["render"] is not None:
            hint = f["render"]
            if not isinstance(hint, str):
                rep.error(where, "'render' must be a string")
            elif not is_x(hint) and hint not in RENDER_HINTS.get(ftype, set()):
                rep.error(where, f"render hint {hint!r} is not registered for {ftype!r} and not x- prefixed (§8.5)")

        rep.section = "§8.3"
        check_constraints(f, rep, where)
        rep.section = "§8"

        # visible_when (§10)
        vw = f.get("visible_when")
        if vw is not None:
            w = f"{where}.visible_when"
            if not isinstance(vw, dict):
                rep.error(w, "must be an object")
                continue
            trig, op = vw.get("field_name"), vw.get("operator")
            if not isinstance(trig, str):
                rep.error(w, "'field_name' must be a string")
            elif trig not in by_name:
                if any(isinstance(g, dict) and g.get("name") == trig for g in fields):
                    rep.error(w, f"references {trig!r}, which is not at a smaller index (forward references only, §10.1)")
                else:
                    rep.error(w, f"references unknown field {trig!r} (§16 rule 1)")
            op = ref(op)
            if op not in OPERATORS:
                rep.error(w, f"unknown operator {op!r} (§10)")
            else:
                allowed = OPERATORS[op]
                ttype = by_name.get(trig, {}).get("type") if isinstance(trig, str) else None
                if allowed is not None and ttype is not None and ref(ttype) not in allowed:
                    rep.error(w, f"operator {op!r} cannot test a {ttype!r} trigger (§10)")
                if op in OPERATORS_WITH_VALUES:
                    vals = vw.get("values")
                    if not isinstance(vals, list) or not vals or not all(isinstance(v, str) for v in vals):
                        rep.error(w, f"operator {op!r} requires a non-empty 'values' array of strings (§10)")
                    elif op == "equals" and len(vals) > 1:
                        rep.warn(w, "operator 'equals' only uses values[0]; did you mean 'in'?")
                elif "values" in vw:
                    rep.error(w, f"'values' must be absent for operator {op!r} (§10)")
    return by_name


# ---------------------------------------------------------------------------
# Values (§9, §16 rule 6)
# ---------------------------------------------------------------------------

def taxonomy_path_error(field, path):
    nodes = _list(field.get("taxonomy"))
    for depth, value in enumerate(path):
        match = next((n for n in nodes if isinstance(n, dict) and n.get("value") == value), None)
        if match is None:
            return f"{value!r} is not a taxonomy value at level {depth + 1}"
        nodes = _list(match.get("children"))
    if nodes and field.get("require_full_path", True) is True:
        return "path stops before a leaf but require_full_path is true"
    return None


def _list(v):
    return v if isinstance(v, list) else []


def is_point(v, dims=(2,)):
    return isinstance(v, list) and len(v) in dims and all(is_num(x) for x in v)


def check_value(field, value, rep, where):
    ftype = field.get("type")
    c = field.get("constraints") if isinstance(field.get("constraints"), dict) else {}
    if not isinstance(ftype, str) or is_x(ftype) or ftype not in FIELD_TYPES:
        return
    def bad(msg):
        # Every value error is a §16 rule 6 violation; keep any narrower citation alongside it.
        m = re.search(r" \((§[^)]*)\)$", msg)
        msg = f"{msg[:m.start()]} ({m.group(1)}, §16 rule 6)" if m else f"{msg} (§16 rule 6)"
        rep.error(where, f"{field.get('name')!r} ({ftype}): {msg}")

    if ftype == "boolean":
        if not isinstance(value, bool):
            bad("must be true or false")
    elif ftype in ("text", "url"):
        if not isinstance(value, str):
            return bad("must be a string")
        if is_int(c.get("min_length")) and len(value) < c["min_length"]:
            bad(f"shorter than min_length {c['min_length']}")
        if is_int(c.get("max_length")) and len(value) > c["max_length"]:
            bad(f"longer than max_length {c['max_length']}")
        if isinstance(c.get("format"), str) and not format_ok(c["format"], value):
            bad(f"is not a valid {c['format']}")
        if isinstance(c.get("pattern"), str):
            compiled, err = compile_pattern(c["pattern"])
            if compiled is not None and not compiled.search(value):
                bad(f"does not match pattern {c['pattern']!r}")
    elif ftype == "number":
        if not is_num(value):
            return bad("must be a finite number")
        if is_num(c.get("min")) and value < c["min"]:
            bad(f"below min {c['min']}")
        if is_num(c.get("max")) and value > c["max"]:
            bad(f"above max {c['max']}")
        if is_num(c.get("exclusive_min")) and value <= c["exclusive_min"]:
            bad(f"not greater than exclusive_min {c['exclusive_min']}")
        if is_num(c.get("exclusive_max")) and value >= c["exclusive_max"]:
            bad(f"not less than exclusive_max {c['exclusive_max']}")
        if c.get("integer") is True and not is_whole(value):
            bad("must be a whole number")
        if is_num(c.get("step")) and c["step"] > 0:
            anchor = c["min"] if is_num(c.get("min")) else 0
            try:
                k = (dec(value) - dec(anchor)) / dec(c["step"])
                if k < 0 or k != k.to_integral_value():
                    bad(f"is not {anchor} + k*{c['step']} for an integer k >= 0 (§8.3.2)")
            except (InvalidOperation, ValueError):
                bad("could not be checked against step")
    elif ftype == "single_select":
        options = {o.get("value") for o in _list(field.get("options")) if isinstance(o, dict) and isinstance(o.get("value"), str)}
        if not isinstance(value, str):
            bad("must be an option value string")
        elif value not in options:
            bad(f"{value!r} is not one of the field's option values")
    elif ftype == "multi_select":
        options = {o.get("value") for o in _list(field.get("options")) if isinstance(o, dict) and isinstance(o.get("value"), str)}
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return bad("must be an array of option value strings")
        if len(set(value)) != len(value):
            bad("contains duplicate values")
        for v in value:
            if v not in options:
                bad(f"{v!r} is not one of the field's option values")
        if is_int(c.get("min_items")) and len(value) < c["min_items"]:
            bad(f"fewer than min_items {c['min_items']}")
        if is_int(c.get("max_items")) and len(value) > c["max_items"]:
            bad(f"more than max_items {c['max_items']}")
    elif ftype == "cascading_select":
        if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
            return bad("must be a non-empty array of taxonomy value strings")
        err = taxonomy_path_error(field, value)
        if err:
            bad(err)
    elif ftype == "date":
        if not is_iso_date(value):
            return bad("must be an ISO 8601 date (YYYY-MM-DD)")
        if is_iso_date(c.get("min_date")) and value < c["min_date"]:
            bad(f"before min_date {c['min_date']}")
        if is_iso_date(c.get("max_date")) and value > c["max_date"]:
            bad(f"after max_date {c['max_date']}")
    elif ftype == "json":
        schema = c.get("json_schema")
        if _jsonschema is not None and isinstance(schema, (dict, bool)) and not list(remote_refs(schema)):
            try:
                _jsonschema.Draft202012Validator(schema).validate(value)
            except Exception as exc:  # noqa: BLE001
                bad(f"does not satisfy json_schema: {getattr(exc, 'message', exc)}")
    elif ftype == "bbox":
        if not (isinstance(value, list) and len(value) == 4 and all(is_num(x) for x in value)):
            bad("must be [x, y, width, height]")
    elif ftype == "rotated_bbox":
        if not (isinstance(value, list) and len(value) == 5 and all(is_num(x) for x in value)):
            bad("must be [cx, cy, width, height, theta]")
    elif ftype in ("polygon", "polyline"):
        floor = 3 if ftype == "polygon" else 2
        if not isinstance(value, list) or not all(is_point(p) for p in value):
            return bad("must be an array of [x, y] points")
        if len(value) < floor:
            bad(f"needs at least {floor} points")
        if is_int(c.get("min_points")) and len(value) < c["min_points"]:
            bad(f"fewer than min_points {c['min_points']}")
        if is_int(c.get("max_points")) and len(value) > c["max_points"]:
            bad(f"more than max_points {c['max_points']}")
    elif ftype == "point":
        if not is_point(value, (2, 3)):
            bad("must be [x, y] or [x, y, z]")
    elif ftype == "keypoints":
        roster = {p.get("name") for p in _list(field.get("points")) if isinstance(p, dict) and isinstance(p.get("name"), str)}
        if not isinstance(value, dict):
            return bad("must be an object mapping landmark names to observations")
        for name, obs in value.items():
            if name not in roster:
                bad(f"landmark {name!r} is not in the field's roster")
            if not isinstance(obs, dict) or not is_point(obs.get("position"), (2, 3)):
                bad(f"landmark {name!r} needs a 'position' of 2 or 3 numbers")
            elif "visibility" in obs and ref(obs["visibility"]) not in KEYPOINT_VISIBILITY:
                bad(f"landmark {name!r} has unknown visibility {obs['visibility']!r}")
    elif ftype == "mask":
        if not isinstance(value, dict):
            return bad("must be an RLE object {size, counts}")
        size, counts = value.get("size"), value.get("counts")
        if not (isinstance(size, list) and len(size) == 2 and all(is_int(x) and x >= 0 for x in size)):
            return bad("'size' must be [height, width] non-negative integers")
        if isinstance(counts, str):
            return bad("compressed (string) RLE is not part of this version; use the uncompressed array (§9.5)")
        if not isinstance(counts, list) or not all(is_int(x) and x >= 0 for x in counts):
            return bad("'counts' must be an array of non-negative integers")
        if sum(counts) != size[0] * size[1]:
            bad(f"run lengths sum to {sum(counts)}, expected height*width = {size[0] * size[1]}")
    elif ftype == "bbox3d":
        if not isinstance(value, dict):
            return bad("must be an object {center, size, rotation | quaternion}")
        if not is_point(value.get("center"), (3,)):
            bad("'center' must be 3 numbers")
        if not is_point(value.get("size"), (3,)):
            bad("'size' must be 3 numbers")
        has_rot, has_q = "rotation" in value, "quaternion" in value
        if has_rot == has_q:
            bad("exactly one of 'rotation' or 'quaternion' must be present (§9.3)")
        elif has_rot and not is_point(value["rotation"], (3,)):
            bad("'rotation' must be 3 numbers (radians)")
        elif has_q:
            q = value["quaternion"]
            if not is_point(q, (4,)):
                bad("'quaternion' must be 4 numbers [x, y, z, w]")
            elif abs(math.sqrt(sum(x * x for x in q)) - 1) > 1e-3:
                bad("'quaternion' must be a unit quaternion")


def is_empty_answer(v):
    return v is None or v == "" or v == [] or v == {}


def visible_fields(fields, values_by_name):
    """Visibility per §10.2, evaluated against one annotation's own values."""
    visible = {}
    for f in fields:
        if not isinstance(f, dict) or not isinstance(f.get("name"), str):
            continue
        vw = f.get("visible_when")
        ok = True
        if isinstance(vw, dict):
            trig = ref(vw.get("field_name"))
            tv = values_by_name.get(trig)
            want = vw.get("values") if isinstance(vw.get("values"), list) else []
            op = vw.get("operator")
            if op == "equals":
                holds = bool(want) and tv == want[0]
            elif op == "in":
                holds = isinstance(tv, (str, int, float, bool)) and tv in want
            elif op == "contains_any":
                holds = isinstance(tv, list) and any(isinstance(x, str) and x in want for x in tv)
            elif op == "is_true":
                holds = tv is True
            elif op == "is_false":
                holds = tv is False
            elif op == "is_answered":
                holds = not is_empty_answer(tv)
            else:
                holds = True
            ok = holds and visible.get(trig, False)
        visible[f["name"]] = ok
    return visible


# ---------------------------------------------------------------------------
# Files, parts, categories (§5, §6, §7, §11, §14)
# ---------------------------------------------------------------------------

def check_info(doc, rep):
    rep.section = "§4"
    info = doc.get("info")
    if info is None:
        rep.warn("info", "missing (§3 lists 'info' as a top-level key)")
        return
    if not isinstance(info, dict):
        rep.error("info", "must be an object")
        return
    for key in ("description", "version", "contributor", "url"):
        if info.get(key) is not None and not isinstance(info[key], str):
            rep.error(f"info.{key}", "must be a string")
    if info.get("year") is not None and not is_num(info["year"]):
        rep.error("info.year", "must be a number")
    if info.get("date_created") is not None and not is_iso_datetime(info["date_created"]):
        rep.error("info.date_created", "must be an ISO 8601 datetime")
    ont = info.get("ontology")
    if ont is not None:
        if not isinstance(ont, dict):
            rep.error("info.ontology", "must be an object")
        else:
            for key in ("name", "description"):
                if ont.get(key) is not None and not isinstance(ont[key], str):
                    rep.error(f"info.ontology.{key}", "must be a string")
            if ont.get("version") is not None and not (is_num(ont["version"]) or isinstance(ont["version"], str)):
                rep.error("info.ontology.version", "must be a number or string")


def check_files(doc, rep):
    rep.section = "§5"
    files = {}
    for i, f in enumerate(doc.get("files") or []):
        where = f"files[{i}]"
        if not isinstance(f, dict):
            rep.error(where, "file must be an object")
            continue
        fid = f.get("id")
        if not is_pos_int(fid):
            rep.error(where, "'id' must be a positive integer")
        elif fid in files:
            rep.error(where, f"duplicate file id {fid} (§16 rule 2)")
        else:
            files[fid] = f
        if not isinstance(f.get("file_name"), str) or not f["file_name"]:
            rep.error(where, "'file_name' must be a non-empty string")
        ft = f.get("file_type")
        if not isinstance(ft, str) or not ft:
            rep.error(where, "'file_type' must be a non-empty string")
        elif ft != ft.lower() or ft.startswith("."):
            rep.error(where, f"file_type {ft!r} must be a lowercase extension without the dot (§5)")
        for key in ("source_id", "uri"):
            if f.get(key) is not None and not isinstance(f[key], str):
                rep.error(f"{where}.{key}", "must be a string")
        for key in ("width", "height", "fps", "duration_seconds"):
            if f.get(key) is not None and not is_num(f[key]):
                rep.error(f"{where}.{key}", "must be a number")
        if f.get("frame_count") is not None and not is_int(f["frame_count"]):
            rep.error(f"{where}.frame_count", "must be an integer")
    return files


def check_parts(doc, files, rep):
    rep.section = "§6"
    parts = {}
    raw = doc.get("parts") or []
    for i, p in enumerate(raw):
        where = f"parts[{i}]"
        if not isinstance(p, dict):
            rep.error(where, "part must be an object")
            continue
        pid = p.get("id")
        if not is_pos_int(pid):
            rep.error(where, "'id' must be a positive integer")
        elif pid in parts:
            rep.error(where, f"duplicate part id {pid} (§16 rule 2)")
        else:
            parts[pid] = (i, p)

    file_parts, frame_parts = set(), set()
    source_ids = {}  # (file_id, row sheet or None, source_id) -> part id (§6, §16 rule 2)
    for pid, (i, p) in parts.items():
        where = f"parts[{i}] (id {pid})"
        ptype, fid = p.get("type"), p.get("file_id")
        if ref(fid) not in files:
            rep.error(where, f"file_id {fid!r} does not reference a file (§16 rule 1)")
        if not isinstance(ptype, str):
            rep.error(where, "'type' is required and must be a string (§6)")
            continue
        if ptype not in PART_TYPES and not is_x(ptype):
            rep.error(where, f"part type {ptype!r} is not registered and not x- prefixed (§7)")
        if p.get("name") is not None and not isinstance(p["name"], str):
            rep.error(where, "'name' must be a string")
        if p.get("source_id") is not None:  # null reads as absent, as on files (§5)
            sid = p["source_id"]
            if not isinstance(sid, str) or not sid:
                rep.error(where, "'source_id' must be a non-empty string; omit it when there is no identifier (§6)")
            else:
                # Row parts are scoped per sheet: a workbook's sheets are separate tables.
                loc = p.get("locator")
                sheet = loc.get("sheet") if p.get("type") == "row" and isinstance(loc, dict) else None
                key = (ref(fid), sheet, sid)
                if key in source_ids:
                    scope = "sheet" if p.get("type") == "row" else "file"
                    rep.error(where, f"source_id {sid!r} is already used by part {source_ids[key]} of the same {scope} (§16 rule 2)")
                else:
                    source_ids[key] = pid
        if "keyframe" in p and p["keyframe"] is not None:
            if not isinstance(p["keyframe"], bool):
                rep.error(where, "'keyframe' must be a boolean")
            if ptype != "region":
                rep.error(where, "'keyframe' appears only on region parts (§16 rule 3)")
        if isinstance(p.get("extra"), dict) and "keyframe" in p["extra"]:
            rep.warn(where, "extra.keyframe is the deprecated legacy form; emit the defined 'keyframe' field (§14.3)")

        # locator (§7)
        loc = p.get("locator")
        spec = LOCATORS.get(ptype, "x")
        if spec is None:
            if loc is not None:
                rep.error(where, f"{ptype} parts must omit 'locator' (§7)")
        elif spec != "x":
            req, opt = spec
            if not isinstance(loc, dict):
                rep.error(where, f"{ptype} parts require a 'locator' object (§7)")
            else:
                for key in req:
                    if key not in loc:
                        rep.error(where, f"locator is missing required {key!r} (§7)")
                for key in loc:
                    if key not in req and key not in opt:
                        rep.warn(where, f"locator key {key!r} is not defined for {ptype} parts")
                rep.section = "§7"
                check_locator(ptype, loc, rep, where)
                rep.section = "§6"
        if ptype == "file":
            if ref(fid) in file_parts:
                rep.error(where, f"more than one file part for file {fid} (§16 rule 3)")
            file_parts.add(ref(fid))
        if ptype == "frame" and isinstance(loc, dict) and is_int(loc.get("frame_index")):
            key = (ref(fid), loc["frame_index"])
            if key in frame_parts:
                rep.error(where, f"more than one frame part for frame_index {loc['frame_index']} (§16 rule 3)")
            frame_parts.add(key)

        # links (§6, §16 rules 4-5)
        parent = ref(p.get("parent_part_id"))
        if parent is not None:
            if parent not in parts:
                rep.error(where, f"parent_part_id {parent!r} does not reference a part (§16 rule 1)")
            else:
                pp = parts[parent][1]
                if pp.get("file_id") != fid:
                    rep.error(where, "parent part belongs to a different file (§16 rule 4)")
                check_containment(p, pp, rep, where)
        track = ref(p.get("track_id"))
        if track is not None:
            if track not in parts:
                rep.error(where, f"track_id {track!r} does not reference a part (§16 rule 1)")
            else:
                tp = parts[track][1]
                if tp.get("type") != "track":
                    rep.error(where, f"track_id {track} references a {tp.get('type')!r} part, not a track (§16 rule 5)")
                if tp.get("file_id") != fid:
                    rep.error(where, "track belongs to a different file (§16 rule 5)")
            if ptype == "track":
                rep.error(where, "track parts must not carry track_id (§16 rule 5)")

    # cycles (§16 rule 4)
    for pid in parts:
        seen, cur = set(), pid
        while cur is not None and cur in parts:
            if cur in seen:
                rep.error(f"part {pid}", "parent_part_id chain forms a cycle (§16 rule 4)")
                break
            seen.add(cur)
            cur = ref(parts[cur][1].get("parent_part_id"))
    return {pid: p for pid, (_i, p) in parts.items()}


def check_locator(ptype, loc, rep, where):
    def nonneg_int(key):
        if key in loc and not (is_int(loc[key]) and loc[key] >= 0):
            rep.error(where, f"locator {key!r} must be a zero-based non-negative integer (§7)")

    if ptype == "mesh":
        np_ = loc.get("node_path")
        if not isinstance(np_, str):
            rep.error(where, "locator 'node_path' must be a string")
        else:
            err = node_path_error(np_)
            if err:
                rep.error(where, f"node_path {np_!r} {err} (§7)")
        nonneg_int("mesh_index")
    elif ptype == "row":
        nonneg_int("row_index")
        if "sheet" in loc and not isinstance(loc["sheet"], str):
            rep.error(where, "locator 'sheet' must be a string")
    elif ptype == "frame":
        nonneg_int("frame_index")
        if "timestamp" in loc and not is_num(loc["timestamp"]):
            rep.error(where, "locator 'timestamp' must be a number (seconds)")
    elif ptype == "page":
        nonneg_int("page_index")
    elif ptype == "span":
        nonneg_int("start_char")
        nonneg_int("end_char")
        if is_int(loc.get("start_char")) and is_int(loc.get("end_char")) and loc["start_char"] > loc["end_char"]:
            rep.error(where, "span start_char is after end_char (§7)")
    elif ptype == "segment":
        has_time = "start_time" in loc or "end_time" in loc
        has_frame = "start_frame" in loc or "end_frame" in loc
        if not has_time and not has_frame:
            rep.error(where, "segment locator needs start_time + end_time or start_frame + end_frame (§7)")
        if has_time:
            if not (is_num(loc.get("start_time")) and is_num(loc.get("end_time"))):
                rep.error(where, "segment start_time and end_time must both be numbers (§7)")
            elif loc["start_time"] > loc["end_time"]:
                rep.error(where, "segment start_time is after end_time (§7)")
        if has_frame:
            if not (is_int(loc.get("start_frame")) and is_int(loc.get("end_frame"))):
                rep.error(where, "segment start_frame and end_frame must both be integers (§7)")
            elif loc["start_frame"] > loc["end_frame"]:
                rep.error(where, "segment start_frame is after end_frame (§7)")


def check_containment(child, parent, rep, where):
    cl, pl = child.get("locator"), parent.get("locator")
    if not isinstance(cl, dict) or not isinstance(pl, dict):
        return
    cnp, pnp = cl.get("node_path"), pl.get("node_path")
    if isinstance(cnp, str) and isinstance(pnp, str) and not cnp.startswith(pnp + "/"):
        rep.error(where, f"node_path {cnp!r} does not extend its parent's {pnp!r} (§6, §16 rule 4)")
    if child.get("type") == parent.get("type") == "segment":
        for a, b in (("start_time", "end_time"), ("start_frame", "end_frame")):
            if all(is_num(x.get(k)) for x in (cl, pl) for k in (a, b)):
                if cl[a] < pl[a] or cl[b] > pl[b]:
                    rep.error(where, f"segment {a}/{b} range is outside its parent segment (§16 rule 4)")
    if child.get("type") == parent.get("type") == "span":
        if all(is_int(x.get(k)) for x in (cl, pl) for k in ("start_char", "end_char")):
            if cl["start_char"] < pl["start_char"] or cl["end_char"] > pl["end_char"]:
                rep.error(where, "span range is outside its parent span (§16 rule 4)")


def check_categories(doc, rep):
    rep.section = "§11"
    cats = set()
    for i, c in enumerate(doc.get("categories") or []):
        where = f"categories[{i}]"
        if not isinstance(c, dict):
            rep.error(where, "category must be an object")
            continue
        cid = c.get("id")
        if not is_pos_int(cid):
            rep.error(where, "'id' must be a positive integer")
        elif cid in cats:
            rep.error(where, f"duplicate category id {cid} (§16 rule 2)")
        else:
            cats.add(cid)
        if not isinstance(c.get("name"), str) or not c["name"]:
            rep.error(where, "'name' must be a non-empty string")
        for key in ("label", "supercategory", "color"):
            if c.get(key) is not None and not isinstance(c[key], str):
                rep.error(f"{where}.{key}", "must be a string")
    return cats


# ---------------------------------------------------------------------------
# Annotations (§12, §16 rules 6-9)
# ---------------------------------------------------------------------------

# ===========================================================================
# VERSION-SPECIFIC RULES (since v0.5) — answers vs. opinions (§12.2), provenance
# (§12.3), and the resolved-region geometry rule (§12.1). Everything outside
# this section is shared, unchanged, by the validators of every version.
# ===========================================================================

def document_is_multi(anns):
    """§12.2: a document is multi-opinion iff any annotation carries `resolved`."""
    return any("resolved" in a for a in anns)


def check_resolved_flag(ann, multi, rep, where):
    if "resolved" in ann and not isinstance(ann["resolved"], bool):
        rep.error(where, "'resolved' must be a boolean (§12)")
    if multi and "resolved" not in ann:
        rep.warn(where, "multi-opinion documents SHOULD write 'resolved' explicitly on every annotation; absent reads as false (§12.2)")


def check_provenance(ann, ann_ids, rep, where, multi):
    prov = ann.get("provenance")
    if prov is None:
        return
    if not isinstance(prov, dict):
        rep.error(where, "'provenance' must be an object")
        return
    for key in ("source", "author", "role"):
        if prov.get(key) is not None and not isinstance(prov[key], str):
            rep.error(f"{where}.provenance.{key}", "must be a string")
    if prov.get("created_at") is not None and not is_iso_datetime(prov["created_at"]):
        rep.error(f"{where}.provenance.created_at", "must be an ISO 8601 datetime")
    if prov.get("source") == "review":
        rep.warn(f"{where}.provenance", "source 'review' is the retired v0.3 form; use source 'human', role 'reviewer' (§12.3)")
    if isinstance(prov.get("author"), str) and _EMAIL_RE.match(prov["author"]):
        rep.warn(f"{where}.provenance.author", "looks like an email address; prefer an opaque non-personal id (§12.3)")
    if "resolved" in prov:
        rep.warn(f"{where}.provenance", "'provenance.resolved' is the v0.4 location; producers must emit the top-level 'resolved' (§12.3)")
    refs = prov.get("from_annotation_ids")
    if refs is not None:
        if not isinstance(refs, list) or not all(is_int(r) for r in refs):
            rep.error(f"{where}.provenance.from_annotation_ids", "must be an array of annotation ids")
        else:
            for r in refs:
                if r == ann.get("id"):
                    rep.error(f"{where}.provenance.from_annotation_ids", "must not reference the annotation itself (§16 rule 9)")
                elif ref(r) not in ann_ids:
                    rep.error(f"{where}.provenance.from_annotation_ids", f"{r} does not reference an annotation (§16 rule 9)")
    if multi and ann.get("resolved") is not True and prov.get("created_at") is None:
        rep.warn(f"{where}.provenance", "opinions in a multi-opinion document SHOULD set created_at so timestamp-based policies work (§12.2)")


def answers_for_part(pid, group, multi, rep):
    """Return the part's answers — the annotations `required` is enforced on (§12.2, §16 rules 8-9)."""
    if multi:
        answers = [(w, a) for w, a in group if a.get("resolved") is True]
        if len(answers) > 1:
            rep.error(f"part {pid}", f"{len(answers)} annotations are resolved: true; at most one answer per part (§12.2, §16 rule 9)")
        return answers
    if len(group) > 1:
        rep.error(f"part {pid}", f"{len(group)} annotations but no 'resolved' flags; a simple document has at most one annotation per part, a multi-opinion document marks its answers with 'resolved' (§12.2, §16 rule 9)")
    return group


def check_region_answer_geometry(pid, geo, answers, multi, rep):
    """§12.1: a resolved region's geometry-defining annotation is its resolved: true one."""
    if multi and answers and len(geo) == 1 and geo[0] is not answers[0][1]:
        rep.error(f"part {pid}", "a resolved region's geometry must be carried by its resolved: true annotation (§12.1, §16 rule 7)")


GEOMETRY_RULE_HINT = "exactly one is required, and each drawing is its own region part"

# ===========================================================================
# End of version-specific rules
# ===========================================================================


def check_annotations(doc, parts, fields_by_name, cats, rep):
    rep.section = "§12"
    fields = [f for f in doc.get("fields") or [] if isinstance(f, dict)]
    fields_by_id = {f.get("id"): f for f in fields if is_pos_int(f.get("id"))}
    anns = [a for a in doc.get("annotations") or [] if isinstance(a, dict)]
    for i, a in enumerate(doc.get("annotations") or []):
        if not isinstance(a, dict):
            rep.error(f"annotations[{i}]", "annotation must be an object")
    ann_ids = set()
    for i, a in enumerate(anns):
        aid = a.get("id")
        if not is_pos_int(aid):
            rep.error(f"annotations[{i}]", "'id' must be a positive integer")
        elif aid in ann_ids:
            rep.error(f"annotations[{i}]", f"duplicate annotation id {aid} (§16 rule 2)")
        else:
            ann_ids.add(aid)

    multi = document_is_multi(anns)

    by_part = {}
    for i, a in enumerate(anns):
        where = f"annotations[{i}] (id {a.get('id')})"
        pid = ref(a.get("part_id"))
        if pid not in parts:
            rep.error(where, f"part_id {pid!r} does not reference a part (§16 rule 1)")
        else:
            by_part.setdefault(pid, []).append((where, a))
        if a.get("category_id") is not None and ref(a["category_id"]) not in cats:
            rep.error(where, f"category_id {a['category_id']!r} does not reference a category (§16 rule 1)")
        check_resolved_flag(a, multi, rep, where)
        vals = a.get("values")
        if not isinstance(vals, list):
            rep.error(where, "'values' must be an array")
            a["_values"] = {}
        else:
            seen, by_field = set(), {}
            for j, v in enumerate(vals):
                w = f"{where}.values[{j}]"
                if not isinstance(v, dict) or "field_id" not in v or "value" not in v:
                    rep.error(w, "value entries must be {field_id, value} objects")
                    continue
                fid = ref(v["field_id"])
                if fid not in fields_by_id:
                    rep.error(w, f"field_id {fid!r} does not reference a field (§16 rule 1)")
                    continue
                if fid in seen:
                    rep.error(w, f"field_id {fid} appears more than once in this annotation (§16 rule 6)")
                    continue
                seen.add(fid)
                by_field[fid] = v["value"]
                check_value(fields_by_id[fid], v["value"], rep, w)
            a["_values"] = by_field
        rep.section = "§12.3"
        check_provenance(a, ann_ids, rep, where, multi)
        rep.section = "§12"

    # Which part types answer which fields (for the `required` scoping noted in the docstring).
    answered_types = {}
    for pid, group in by_part.items():
        ptype = ref(parts[pid].get("type"))
        for _w, a in group:
            for fid in a["_values"]:
                answered_types.setdefault(ptype, set()).add(fid)
    single_kind = len(answered_types) <= 1

    for pid, group in by_part.items():
        part = parts[pid]
        ptype = ref(part.get("type"))
        answers = answers_for_part(pid, group, multi, rep)

        # Geometry rule (§12.1, §16 rule 7)
        geo = []
        for w, a in group:
            gvals = [fid for fid in a["_values"] if ref(fields_by_id[fid].get("type")) in GEOMETRY_TYPES]
            if gvals and ptype != "region":
                rep.error(w, f"geometry values appear only on region parts; part {pid} is a {ptype!r} (§12.1, §16 rule 7)")
            if len(gvals) > 1:
                rep.error(w, "an annotation carries at most one geometry value (§12.1, §16 rule 7)")
            if gvals:
                geo.append(a)
        if ptype == "region":
            if len(geo) != 1:
                rep.error(f"part {pid}", f"region part has {len(geo)} geometry-defining annotations; {GEOMETRY_RULE_HINT} (§12.1, §16 rule 7)")
            check_region_answer_geometry(pid, geo, answers, multi, rep)

        # Conditional requiredness on answers (§10.2, §16 rule 8)
        for w, a in answers:
            values_by_name = {ref(fields_by_id[fid].get("name")): v for fid, v in a["_values"].items()}
            visible = visible_fields(fields, values_by_name)
            for f in fields:
                name = ref(f.get("name"))
                if ref(f.get("type")) in GEOMETRY_TYPES or not visible.get(name, False):
                    continue
                if f.get("required") is True and is_empty_answer(values_by_name.get(name)):
                    if single_kind or ref(f.get("id")) in answered_types.get(ptype, set()):
                        rep.error(w, f"required field {name!r} is visible but unanswered (§10.2, §16 rule 8)")
        for w, a in group:
            values_by_name = {ref(fields_by_id[fid].get("name")): v for fid, v in a["_values"].items()}
            visible = visible_fields(fields, values_by_name)
            for name in values_by_name:
                if name in visible and not visible[name]:
                    rep.warn(w, f"value for hidden field {name!r}; producers should omit hidden values (§10.2)")

    for a in anns:
        a.pop("_values", None)
    return multi


# ---------------------------------------------------------------------------
# Document entry point
# ---------------------------------------------------------------------------

def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


def _no_duplicate_keys(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate object key {k!r}")
        out[k] = v
    return out


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant)


def validate(doc):
    """Validate a parsed document. Returns a Report."""
    rep = Report()
    if not isinstance(doc, dict):
        rep.error("$", "a JAMESON document is a single JSON object (§3)")
        return rep
    version = doc.get("jameson_version")
    if not isinstance(version, str):
        rep.error("jameson_version", "is required and must be a string (§3)")
        return rep
    if version != VERSION:
        rep.error("jameson_version", f"is {version!r}; this validator checks {VERSION!r} only — use v{version}/validate.py (§3)")
        return rep
    for key in ("files", "parts", "fields", "categories", "annotations"):
        if key not in doc:
            rep.error(key, "is required (it may be an empty array) (§3)")
        elif not isinstance(doc[key], list):
            rep.error(key, "must be an array (§3)")
    if rep.errors:
        return rep

    check_info(doc, rep)
    files = check_files(doc, rep)
    parts = check_parts(doc, files, rep)
    fields_by_name = check_fields(doc, rep)
    cats = check_categories(doc, rep)
    check_annotations(doc, parts, fields_by_name, cats, rep)

    if not doc["files"] and not doc["parts"] and not doc["annotations"] and doc["fields"]:
        ont = (doc.get("info") or {}).get("ontology") if isinstance(doc.get("info"), dict) else None
        if not isinstance(ont, dict) or not ont.get("name"):
            rep.warn("info.ontology.name", "recommended on ontology documents so imports are idempotent (§13)")
    return rep


def validate_path(path):
    """Returns (report or None, load error or None)."""
    try:
        doc = load(path)
    except OSError as exc:
        return None, str(exc)
    except ValueError as exc:
        return None, f"{exc} (§3: a JAMESON document is a single valid JSON object)"
    return validate(doc), None


# ---------------------------------------------------------------------------
# Self-test: every file in examples/ must validate, and every case listed in
# tests/manifest.json must give its expected result. An invalid case passes
# only when some error cites the case's `rule`.
# ---------------------------------------------------------------------------

def _run_case(path, expect_valid, rule):
    rep, err = validate_path(path)
    errors = [err] if err else rep.errors
    if expect_valid:
        return not errors, errors
    return any(rule in e for e in errors), errors or ["no errors"]


def self_test():
    here = Path(__file__).resolve().parent
    cases = [(p, True, None, "example") for p in sorted((here / "examples").glob("*.json"))]
    manifest_path = here / "tests" / "manifest.json"
    if manifest_path.exists():
        manifest = load(manifest_path)
        listed = set()
        for case in manifest["cases"]:
            path = here / "tests" / case["file"]
            listed.add(path)
            cases.append((path, case["valid"], case.get("rule"), "valid" if case["valid"] else "invalid"))
        for path in sorted((here / "tests").glob("*/*.json")):
            if path not in listed:
                cases.append((path, None, None, "unlisted"))

    failed = 0
    for path, expect_valid, rule, kind in cases:
        name = path.relative_to(here)
        if kind == "unlisted":
            print(f"FAIL  {name} is not listed in tests/manifest.json")
            failed += 1
            continue
        ok, errors = _run_case(path, expect_valid, rule)
        label = f"{kind:<8} {name}" + (f"  [{rule}]" if rule else "")
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            failed += 1
            if not expect_valid:
                print(f"        expected an error citing {rule!r}")
            for line in errors:
                print(f"        {line}")
    print(f"\n{len(cases) - failed} of {len(cases)} passed" + ("" if not failed else f"; {failed} failed"))
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=f"Validate JAMESON v{VERSION} documents against the v{VERSION} specification."
    )
    parser.add_argument("files", nargs="*", help="JAMESON JSON files to validate")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    parser.add_argument("--quiet", action="store_true", help="print only the per-file result line")
    parser.add_argument("--self-test", action="store_true", help="validate this folder's examples and broken copies of them")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.files:
        parser.print_usage(sys.stderr)
        return 2

    status = 0
    for path in args.files:
        rep, err = validate_path(path)
        if err is not None:
            print(f"ERROR    {path}: cannot read as JSON: {err}")
            status = max(status, 2)
            continue
        failed = bool(rep.errors) or (args.strict and bool(rep.warnings))
        print(f"{'INVALID' if failed else 'VALID'}  {path}  ({len(rep.errors)} error(s), {len(rep.warnings)} warning(s))")
        if not args.quiet:
            for line in rep.errors:
                print(f"  error    {line}")
            for line in rep.warnings:
                print(f"  warning  {line}")
        if failed:
            status = max(status, 1)
    if _re2 is None and _jsonschema is None and not args.quiet:
        print("note: install google-re2 and jsonschema for exact pattern and json_schema checks", file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
