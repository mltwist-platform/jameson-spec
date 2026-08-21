**JAMESON Annotation Format**
**Specification Draft v0.4**
August 20, 2026

---

### 1. Overview

JAMESON (**J**SON **A**nnotation **M**odel with **E**mbedded **S**chema and **O**ntology **N**otation) is a general-purpose JSON annotation format designed for multi-modal data labeling. It supports:

- Images with bounding boxes, polygons, and points
- Multi-mesh 3D assets (GLB / glTF) with scene-graph hierarchy
- Spreadsheet / tabular data (rows as labelable units)
- Video (frame-level labeling, multi-object tracking, temporal segments)
- Audio (transcription, speaker diarization, sound-event detection)
- Text (character-span labeling: named-entity recognition, sentence structure, coreference)
- Documents / PDFs (page- and section-level labeling)
- Point clouds and 3D cuboids
- Whole-file QA and classification for any file type
- Rich, self-describing ontologies (typed form fields, taxonomies, conditional visibility)

JAMESON follows the spirit of COCO (multiple files in one document, explicit objects, linked annotations) while fixing its two structural gaps: COCO has no concept of a labelable **sub-unit of a file** (a mesh, a row, a frame), and it carries **no ontology** — attribute schemas live out-of-band, so attribute-rich COCO files do not interoperate. JAMESON solves the first with a generic **parts** model and the second with a formal **fields** system that fully describes the labeling form, making every JAMESON file self-describing and renderable without external schema information.

The name "JAMESON" is intentional and permanent. It is styled in capitals as an acronym — **J**SON **A**nnotation **M**odel with **E**mbedded **S**chema and **O**ntology **N**otation — following the convention of the format it succeeds (COCO, *Common Objects in Context*).

---

### 2. Design Goals

- Support multiple source files in a single annotation document
- Give every labelable unit a stable identity (`parts` with typed `locator`s)
- Support hierarchical structure via `parent_part_id` and cross-cutting identity via `track_id`
- Carry the full ontology inside the document: value types, options, taxonomies, constraints, display metadata, and conditional visibility
- Make every value shape explicit and validatable
- Remain usable for both simple QA ontologies and rich semantic labeling
- Stay extensible without breaking existing files

**Rigidity principle.** JAMESON deliberately avoids the "infinitely flexible" failure mode (cf. FHIR), where two conforming producers are mutually unreadable. Anything a consumer must read to *locate, validate, or render* an annotation is a **defined field with a normative shape** — never free-form metadata. The `extra` objects that appear throughout the spec are for genuinely incidental metadata only (statistics, display niceties, producer bookkeeping). A conforming consumer must be able to fully render a JAMESON file while ignoring every `extra` object. Extensibility is provided through governed registries (part types §7, field types §9, render hints §8.5) with an `x-` prefix escape hatch for experimentation; proven `x-` values are promoted into the registries by minor spec versions.

---

### 3. Top-Level Structure

A valid JAMESON file is a single JSON object with these keys:

```json
{
  "jameson_version": "0.4",
  "info": { ... },
  "files": [ ... ],
  "parts": [ ... ],
  "fields": [ ... ],
  "categories": [ ... ],
  "annotations": [ ... ]
}
```

- All arrays are required (they may be empty).
- Unknown top-level keys should be ignored by consumers for forward compatibility.
- `jameson_version` is required and must be a string.
- A document with empty `files`, `parts`, and `annotations` but populated `fields` (and optionally `categories`) is a valid **ontology document** — see §13.

---

### 4. `info` Object

```json
"info": {
  "description": "GLB quality review for Project X",
  "version": "1.0",
  "year": 2026,
  "contributor": "MLtwist",
  "date_created": "2026-08-15T17:00:00Z",
  "url": null,
  "ontology": {
    "name": "glb-quality-review",
    "version": 7,
    "description": "Mesh-level quality checklist"
  },
  "extra": {}
}
```

| Field          | Type   | Required | Description                               |
| -------------- | ------ | -------- | ----------------------------------------- |
| `description`  | string | no       | Human-readable description of the dataset |
| `version`      | string | no       | Dataset / project version                 |
| `year`         | number | no       |                                           |
| `contributor`  | string | no       | Organization or person                    |
| `date_created` | string | no       | ISO 8601 datetime                         |
| `url`          | string | no       | Optional link to more information         |
| `ontology`     | object | no       | Provenance of the embedded ontology (§4.1) |
| `extra`        | object | no       | Producer bookkeeping (project IDs, export parameters, etc.) |

#### 4.1 `info.ontology`

Identifies the ontology snapshot embedded in `fields`, so a document is traceable back to the schema that produced it and ontology documents (§13) are versionable.

| Field         | Type              | Required | Description                                 |
| ------------- | ----------------- | -------- | ------------------------------------------- |
| `name`        | string            | no       | Stable ontology identifier                  |
| `version`     | number or string  | no       | Ontology version pinned when annotations were produced |
| `description` | string            | no       | Human-readable summary                      |

---

### 5. `files` Array

Each entry represents one **logical source asset**. A multi-file asset (a DICOM series, a `.gltf` with external buffers) is still a single entry.

```json
{
  "id": 1,
  "file_name": "car_001.glb",
  "file_type": "glb",
  "source_id": "8f14e45f-ceea-4e2b-9c5d-0d1b2f3a4c5e",
  "uri": null,
  "width": null,
  "height": null,
  "fps": null,
  "frame_count": null,
  "duration_seconds": null,
  "extra": {
    "num_meshes": 12
  }
}
```

| Field              | Type    | Required | Description                                                |
| ------------------ | ------- | -------- | ---------------------------------------------------------- |
| `id`               | integer | yes      | Unique positive integer within the document                |
| `file_name`        | string  | yes      | Original file name, including relative path and extension  |
| `file_type`        | string  | yes      | Lowercase extension without dot: `"glb"`, `"jpg"`, `"xlsx"`, `"mp4"`, `"pcd"`, `"pdf"`, `"wav"`, `"dicom"`, `"nii"`, … |
| `source_id`        | string  | no       | Producer's stable identifier for this file (e.g. a database UUID). Recommended whenever one exists — `file_name` alone is not a durable identity. |
| `uri`              | string  | no       | Optional retrievable location (URL, storage path)          |
| `width` / `height` | number  | no       | For images and video, in pixels                            |
| `fps`              | number  | no       | For video: frames per second (may be non-integer)          |
| `frame_count`      | integer | no       | For video: total frame count                               |
| `duration_seconds` | number  | no       | For video / audio: duration                                |
| `extra`            | object  | no       | Incidental metadata only (see §2 rigidity principle)       |

For video files, producers should emit `fps` whenever known: `frame_index` and `timestamp` on frame parts are only mutually interpretable given the frame rate, and variable-frame-rate video is why both are stored per frame (§7, §14).

---

### 6. `parts` Array

A **part** is any discrete unit that can receive annotations: a whole file, a mesh, a spreadsheet row, a video frame, a drawn region instance, a track identity, a temporal segment, a document page.

```json
{
  "id": 102,
  "file_id": 1,
  "name": "Wheel_FL",
  "type": "mesh",
  "parent_part_id": 101,
  "track_id": null,
  "locator": {
    "node_path": "Root/Body[0]/Wheel_FL[3]"
  },
  "extra": {}
}
```

| Field            | Type            | Required | Description                                                                      |
| ---------------- | --------------- | -------- | -------------------------------------------------------------------------------- |
| `id`             | integer         | yes      | Unique positive integer within the document                                      |
| `file_id`        | integer         | yes      | References `files[].id`                                                          |
| `type`           | string          | yes      | Part type from the registry in §7 (or an `x-` prefixed experimental type)        |
| `name`           | string          | no       | Human-readable name                                                              |
| `parent_part_id` | integer or null | no       | Structural containment (see below). `null` / absent = top-level                  |
| `track_id`       | integer or null | no       | References a part with `type: "track"` in the same file — cross-frame / cross-region identity (§14) |
| `keyframe`       | boolean         | no       | `region` parts only, default `false`: marks a keyframe observation eligible for interpolation (§14.3) |
| `locator`        | object          | per-type | The part's address **within the source file's own reference system**. Required shape is defined per part type in §7. |
| `extra`          | object          | no       | Incidental metadata only — never identity, never geometry                        |

**Two linkage fields, two meanings — never mixed:**

- `parent_part_id` always means **structural containment**: a mesh inside an assembly, a region inside a frame, a section inside a page. It forms a tree (each part has at most one parent; no cycles).
- `track_id` always means **same real-world instance**: this region part and that region part are observations of one object. It is a cross-link, not a parent, so a part can simultaneously live in the containment tree *and* belong to a track.

**Hierarchy and locators are complementary, not redundant.** The `parent_part_id` tree lets a consumer work with the document's structure without parsing the source file at all; the `locator` anchors each part into the actual asset so a viewer can highlight the real mesh, row, or frame. Where both encode the same structure (e.g. a GLB scene graph), they must agree: a child's `locator.node_path` must extend its parent's (§16).

---

### 7. Part Type Registry

`type` is drawn from this registry. Each type defines its required `locator` shape — this is what a validator enforces and what makes producers interoperable. Types not listed here must be prefixed `x-` (e.g. `"x-mltwist-scene"`).

| `type`    | Locator: required fields | Locator: optional fields | Meaning |
| --------- | ------------------------ | ------------------------ | ------- |
| `file`    | — (omit `locator`)       | —                        | The whole file. At most one per `file_id`. |
| `mesh`    | `node_path` (string)     | `mesh_index` (integer)   | A node in a 3D asset's scene graph. |
| `row`     | `row_index` (integer)    | `sheet` (string)         | A spreadsheet / table row. `sheet` required for multi-sheet files. |
| `frame`   | `frame_index` (integer)  | `timestamp` (number, seconds) | A single video frame. At most one per `(file_id, frame_index)`. |
| `track`   | — (omit `locator`)       | —                        | An object identity across frames or regions. Referenced via `track_id`. |
| `segment` | `start_time` + `end_time` (numbers, seconds) **or** `start_frame` + `end_frame` (integers) | the other pair | A temporal interval (action, event, audio span). Frame fields are authoritative when both pairs are present. |
| `region`  | — (omit `locator`)       | —                        | A drawn geometric instance (2D or 3D). Its extent is defined by the geometry value on its annotation (§12.1). |
| `page`    | `page_index` (integer)   | —                        | A document / PDF page. |
| `span`    | `start_char` + `end_char` (integers) | —            | A character range in a text document (§14.7). |

**Indexing conventions (normative):**

- All indices are **zero-based**: `frame_index`, `row_index`, `page_index`, and the `[n]` child indices inside `node_path`.
- `row_index` counts **physical rows including headers**. Header handling is a producer concern; the display row number may go in `extra`.
- `node_path` is the `/`-joined path of node names from the scene root, where every path element except the root carries its child index in square brackets: `Root/Body[0]/Wheel_FL[3]`. The index disambiguates same-named siblings and is required even when the name is unique. Node names containing `/`, `[`, or `]` must escape them with a backslash.
- `timestamp`, `start_time`, `end_time` are seconds from the start of the file. `timestamp` is derived display data; `frame_index` is the value of record.
- `start_char` / `end_char` are zero-based offsets in **Unicode code points** into the file's decoded text; `end_char` is exclusive (the span covers `[start_char, end_char)`). Not UTF-16 code units, not bytes — offset-unit ambiguity is the classic text-annotation interoperability failure, so the unit is normative.

**Registry evolution:** minor spec versions may add types (candidates: `paragraph`, `channel` for audio, `slice` for medical volumes). Consumers must treat unknown types as opaque — preserve them, do not attempt to render them.

---

### 8. `fields` Array — the Ontology

This section is the heart of JAMESON's self-description: it declares every field **once**, with enough type, constraint, and display information that a consumer can render the complete labeling form — dropdowns, taxonomies, conditional fields — from the document alone, and validate every value in `annotations` against it. This is the capability COCO structurally lacks (COCO's `categories` is its entire schema; attribute dictionaries have no declared types and do not interoperate).

```json
{
  "id": 3,
  "name": "damage_type",
  "label": "Damage Type",
  "description": "Primary visible damage on this part",
  "type": "single_select",
  "required": true,
  "options": [
    { "value": "scratch", "label": "Scratch" },
    { "value": "dent", "label": "Dent" },
    { "value": "missing", "label": "Missing / Absent", "description": "Part not present in the asset" }
  ],
  "visible_when": {
    "field_name": "is_damaged",
    "operator": "is_true"
  },
  "render": "radio",
  "constraints": {},
  "extra": {}
}
```

| Field          | Type    | Required | Description                                                       |
| -------------- | ------- | -------- | ----------------------------------------------------------------- |
| `id`           | integer | yes      | Unique positive integer within the document                       |
| `name`         | string  | yes      | Stable machine name, unique within the document. snake_case recommended. Referenced by `visible_when.field_name`. |
| `label`        | string  | no       | Human display name. Defaults to `name`.                           |
| `description`  | string  | no       | Help text shown to labelers / readers                             |
| `type`         | string  | yes      | Value type from the registry in §9                                |
| `required`     | boolean | no       | Default `false`. Enforced **only while the field is visible** (§10.2). |
| `options`      | array   | for select types | Array of option objects (§8.1). Required for `single_select` / `multi_select`; forbidden elsewhere. |
| `levels`       | array   | for `cascading_select` | Ordered level descriptors (§8.2)                       |
| `taxonomy`     | array   | for `cascading_select` | Recursive option tree (§8.2)                           |
| `require_full_path` | boolean | no  | `cascading_select` only, default `true` (§8.2)                    |
| `points`       | array   | for `keypoints` | Ordered named landmark descriptors (§9.4)                     |
| `skeleton`     | array   | no       | `keypoints` only: landmark connectivity for rendering (§9.4)      |
| `visible_when` | object  | no       | Conditional visibility clause (§10)                               |
| `constraints`  | object  | no       | Per-type value constraints (§8.3)                                 |
| `render`       | string  | no       | UI rendering hint (§8.5). Consumers may ignore it; it never changes the value shape. |
| `extra`        | object  | no       | Incidental metadata only                                          |

**Ordering is meaningful (normative):** the array order of `fields` is the display order of the form. `visible_when` may only reference fields at a strictly smaller index (§10.1), so order also guarantees the dependency graph is acyclic.

#### 8.1 Option objects

Options for `single_select` and `multi_select` are always objects — never bare strings — so machine values and display labels are both first-class:

```json
{ "value": "credit_note", "label": "Credit Note", "description": null, "color": null, "extra": {} }
```

| Field         | Type   | Required | Description                                   |
| ------------- | ------ | -------- | --------------------------------------------- |
| `value`       | string | yes      | Stored machine value, unique within the field |
| `label`       | string | yes      | Display label                                 |
| `description` | string | no       | Help text / tooltip                           |
| `color`       | string | no       | Hex color for visualization                   |
| `extra`       | object | no       |                                               |

Annotation values store only `value` strings.

#### 8.2 Cascading selects

A `cascading_select` is a taxonomy walked one level at a time (e.g. Vehicle → Car → Sedan). Its definition carries everything a consumer needs to render the picker and validate paths:

```json
{
  "id": 5,
  "name": "object_class",
  "label": "Object Class",
  "type": "cascading_select",
  "required": true,
  "require_full_path": true,
  "levels": [
    { "label": "Domain" },
    { "label": "Type" },
    { "label": "Subtype" }
  ],
  "taxonomy": [
    {
      "value": "vehicle", "label": "Vehicle",
      "children": [
        {
          "value": "car", "label": "Car",
          "children": [
            { "value": "sedan", "label": "Sedan" },
            { "value": "suv", "label": "SUV" }
          ]
        },
        { "value": "truck", "label": "Truck" }
      ]
    }
  ]
}
```

- `levels`: ordered array of `{ label }` objects (length >= 2) naming each depth for display.
- `taxonomy`: recursive array of `{ value, label, children? }` nodes. `value` must be unique among siblings.
- `require_full_path` (default `true`): when `true`, every taxonomy branch must reach the last level, and a valid answer selects every level. When `false`, branches may end early and any path that ends at a leaf **or** any valid path prefix is a complete answer. This is independent of `required`, which only governs whether an answer must exist at all.
- The stored value is the ordered array of `value` strings along the chosen path: `["vehicle", "car", "sedan"]` (§9).

#### 8.3 `constraints` object

Per-type validation constraints. Only the keys relevant to the definition's `type` are legal; others must be rejected by validators.

| Constraint     | Applies to        | Type    | Description                                    |
| -------------- | ----------------- | ------- | ---------------------------------------------- |
| `min` / `max`  | `number`          | number  | Inclusive bounds                               |
| `exclusive_min` / `exclusive_max` | `number` | number | Exclusive bounds (e.g. "strictly greater than 0"). At most one bound per side: `min` and `exclusive_min` must not both be present, likewise `max` / `exclusive_max`. |
| `step`         | `number`          | number  | Legal increment (§8.3.2)                       |
| `integer`      | `number`          | boolean | Require whole numbers (§8.3.2)                 |
| `min_length` / `max_length` | `text`, `url` | integer | String length bounds                      |
| `format`       | `text`            | string  | Named format from the registry in §8.3.1. Preferred over `pattern` for common formats. |
| `pattern`      | `text`, `url`     | string  | Safe-subset regular expression the value must match (§8.6) |
| `min_items` / `max_items` | `multi_select` | integer | Bounds on number of selected options      |
| `json_schema`  | `json`            | object  | Embedded JSON Schema (draft 2020-12, self-contained — §8.6) the value must satisfy |
| `min_date` / `max_date` | `date`   | string  | ISO 8601 date bounds                           |
| `min_points` / `max_points` | `polygon`, `polyline` | integer | Bounds on vertex count (polygon floor is 3 regardless) |

##### 8.3.1 Named string formats

For common string shapes, producers should use `format` rather than hand-written patterns: consumers validate named formats with their own vetted validators, which is both safer and more interoperable than trusting producer regexes (every producer writing its own email regex is exactly the divergence JAMESON's rigidity principle forbids). Registered values:

| `format`     | Meaning                                    |
| ------------ | ------------------------------------------ |
| `email`      | RFC 5322 email address                     |
| `phone_e164` | E.164 phone number (`+14155552671`)        |
| `uuid`       | RFC 4122 UUID                              |
| `hostname`   | RFC 1123 hostname                          |
| `ipv4` / `ipv6` | IP address                              |

Unregistered formats must be `x-` prefixed; consumers treat unknown formats as unvalidated (accept any string) and should surface a warning at import. `format` and `pattern` may be combined; both must hold.

##### 8.3.2 Numeric semantics (normative)

- **Step anchor**: a value satisfies `step` iff it equals `min + k * step` for some integer `k >= 0`, anchored at `0` when `min` is absent (`exclusive_min` does not anchor).
- **Decimal evaluation**: step conformance is evaluated in decimal, not binary floating point — implementations must scale by the step's decimal places into integers (or equivalent) before comparing. `0.3` **is** a valid value for `step: 0.1` even though `0.3 !== 3 * 0.1` in IEEE doubles. Two validators disagreeing on step conformance is a conformance bug.
- **Integer coherence**: when `integer: true`, the value and any `min`, `max`, `exclusive_min`, `exclusive_max`, `step` must all be whole numbers.
- **Precision**: JSON numbers are IEEE 754 doubles. Values requiring exact decimal semantics (currency) or magnitudes beyond 2^53 must use `text` (with `format` or `pattern`), not `number`.

#### 8.4 Mapping guidance for producers

A typical labeling-tool ontology maps onto JAMESON fields as follows. The left column is illustrative (field types common across labeling platforms), not part of the spec:

| Source field type | JAMESON `type`     | Notes                                             |
| ----------------- | ------------------ | ------------------------------------------------- |
| Single select (dropdown) | `single_select` | `render: "dropdown"` (default)               |
| Radio group       | `single_select`    | `render: "radio"` — same data, different widget   |
| Multi select      | `multi_select`     |                                                   |
| Free text         | `text`             | `render: "textarea"` for multiline                |
| Number            | `number`           | `constraints.min/max/step/integer`                |
| Checkbox / toggle | `boolean`          | `render: "checkbox"` (default) or `"toggle"`      |
| Date              | `date`             |                                                   |
| URL               | `url`              |                                                   |
| Cascading select  | `cascading_select` | `levels` + `taxonomy` + `require_full_path`       |
| Raw JSON          | `json`             | Optionally `constraints.json_schema`              |
| Box drawing tool  | `bbox`             | Geometry types in an ontology declare the drawing tools a task offers (§12.1 governs where values may appear) |
| Cuboid tool       | `bbox3d`           |                                                   |
| Polygon / path tool | `polygon`, `polyline` | `constraints.min_points` / `max_points`      |
| Pose / landmarks tool | `keypoints`    | `points` + optional `skeleton`                    |
| Mask / brush tool | `mask`             |                                                   |

A labeling tool importing an ontology that contains geometry types it does not yet support should reject the import with a clear message (or import with those tools disabled) — it must not silently drop the definitions.

#### 8.5 `render` hints registry

`render` decouples value shape from widget: two fields can share a `type` (and thus a value shape and validation rule) while rendering differently. Registered values, per type:

| `type`          | Registered `render` values (first = default)  |
| --------------- | --------------------------------------------- |
| `single_select` | `dropdown`, `radio`                           |
| `multi_select`  | `checklist`, `dropdown`, `tags`               |
| `boolean`       | `checkbox`, `toggle`                          |
| `text`          | `input`, `textarea`                           |
| `number`        | `input`, `slider`                             |
| `date`          | `date_picker`                                 |

Unregistered hints must be `x-` prefixed. A consumer that does not recognize a hint falls back to the default widget for the type — a hint never affects validity.

#### 8.6 Constraint Enforcement Contract

Constraints are only meaningful if the same rule is enforceable at three points. A conforming implementation honors all three:

1. **Import** — the ontology itself is validated. A constraint set that is ill-formed (see below) makes the document invalid; importers must reject it with a diagnostic at upload time. *An ontology that imports successfully must be renderable and answerable* — all failure surfaces to the ontology author, never to a labeler facing a form that cannot be completed.
2. **Render** — the generated widget physically honors the constraints (bounds and step wired into number inputs, option lists closed, length limits enforced).
3. **Submit** — the receiving system re-validates every value against the definitions. The UI is never the enforcement boundary; §16 rule 6 applies to all ingested annotations regardless of origin.

**Ill-formed constraint sets (importers must reject):**

- A constraint key not legal for the field's `type` (§8.3)
- An empty legal range: `min > max` (or exclusive-variant equivalents admitting no value), `min_length > max_length`, `min_items > max_items`, `min_date > max_date`, `min_points > max_points`
- Both `min` and `exclusive_min` present (likewise `max` / `exclusive_max`)
- `step <= 0`, or `step`/bounds violating integer coherence (§8.3.2)
- `max_items` exceeding the number of `options`
- Unparseable `min_date` / `max_date`
- A `pattern` that does not compile, or that uses features outside the safe subset below
- A `json_schema` that is not a valid self-contained schema
- `required: true` on a field whose constraints admit no value

**Rules for untrusted ontologies** (required once documents cross organizational boundaries):

- **`pattern` safe subset**: patterns are limited to a linear-time-safe regular-expression subset — no backreferences, no lookahead/lookbehind. (Equivalently: RE2-compatible.) Implementations should additionally bound evaluation time. This prevents a hostile or careless ontology from shipping a catastrophically backtracking pattern that stalls validators (ReDoS).
- **`json_schema` is pinned and self-contained**: JSON Schema draft 2020-12; remote `$ref` is forbidden and validators must never fetch external resources. A JAMESON document is always fully self-contained.

**Deliberate non-features:**

- **No default values.** Fields cannot declare defaults. An absent answer means *untouched* — a default would silently manufacture agreement data labelers never expressed.
- **No cross-field value constraints and no expression language.** `visible_when` (§10) is the only cross-field mechanism. A constraint vocabulary you cannot statically validate is the interoperability trapdoor this spec exists to avoid; anything beyond the closed vocabulary of §8.3 belongs in a future registry revision, not in producer-defined expressions.

---

### 9. Field Types & Value Shapes

Every value must conform to the shape defined by its field's `type`.

#### 9.1 Form value types

| Type               | Value Shape                                        | Example                             |
| ------------------ | -------------------------------------------------- | ----------------------------------- |
| `boolean`          | `true` or `false`                                  | `true`                              |
| `text`             | string                                             | `"Slight scratch on left side"`     |
| `number`           | number                                             | `0.92`                              |
| `single_select`    | string (an option `value`)                         | `"sedan"`                           |
| `multi_select`     | array of strings (option `value`s, no duplicates)  | `["scratch", "dent"]`               |
| `cascading_select` | array of strings (ordered path of taxonomy `value`s from the root) | `["vehicle", "car", "sedan"]` |
| `date`             | string (ISO 8601 date)                             | `"2026-08-15"`                      |
| `url`              | string                                             | `"https://example.com"`             |
| `json`             | any valid JSON                                     | `{ "key": "value" }`                |

#### 9.2 Geometry value types

| Type           | Value Shape                                        | Example                             |
| -------------- | -------------------------------------------------- | ----------------------------------- |
| `bbox`         | array of exactly 4 numbers `[x, y, width, height]` | `[120.5, 340.0, 80.0, 45.5]`        |
| `rotated_bbox` | array of exactly 5 numbers `[cx, cy, width, height, theta]`; `theta` in radians about the center, measured **from the positive x-axis toward the positive y-axis** — which appears clockwise on screen in the y-down pixel frame. (Rotation conventions are where existing formats diverge worst — OpenCV, DOTA, and mmrotate all disagree — so this definition is deliberately exact.) | `[400, 300, 120, 60, 0.35]` |
| `polygon`      | array of >= 3 `[x, y]` points (one ring, implicitly closed) | `[[10,20],[30,20],[30,50],[10,50]]` |
| `polyline`     | array of >= 2 `[x, y]` points (open path, not closed) | `[[10,20],[120,24],[240,31]]`    |
| `point`        | array of 2 or 3 numbers                            | `[100, 200]` or `[1.2, 3.4, 0.5]`   |
| `keypoints`    | object mapping landmark names to observations (§9.4) | —                                 |
| `mask`         | object: COCO-style RLE segmentation (§9.5)         | —                                   |
| `bbox3d`       | object (§9.3)                                      | —                                   |

**2D coordinate frame (normative):** pixel coordinates in the containing image or video frame; origin at the top-left; x increases rightward, y increases downward. Values may be fractional. Coordinates are always **absolute pixels** — normalized (0–1) coordinates are non-conforming.

**3D coordinate frame (normative):** coordinates are expressed in the source asset's own scene/world space. For glTF/GLB that means the glTF convention: right-handed, +Y up, meters. A JAMESON file never re-defines the asset's coordinate system.

`polygon` supports a single ring without holes; multi-polygon and hole support are candidates for a future minor version.

#### 9.3 `bbox3d`

A 3D cuboid is stored as center + size + orientation. JAMESON deliberately does **not** store the 8 corner points: they are derivable, redundant, and permit invalid (non-cuboid) values that validators cannot cheaply detect. This matches established 3D formats (KITTI, nuScenes, Objectron).

```json
{
  "center": [1.2, 0.5, 3.8],
  "size": [4.5, 1.8, 1.6],
  "rotation": [0.0, 1.57, 0.0]
}
```

| Field        | Type                 | Required | Description                                                  |
| ------------ | -------------------- | -------- | ------------------------------------------------------------ |
| `center`     | array of 3 numbers   | yes      | Cuboid center `[x, y, z]`                                    |
| `size`       | array of 3 numbers   | yes      | Full extents `[sx, sy, sz]` along the cuboid's local axes    |
| `rotation`   | array of 3 numbers   | one of   | Euler angles in **radians**, applied in **intrinsic X-Y-Z order** |
| `quaternion` | array of 4 numbers   | one of   | Unit quaternion `[x, y, z, w]`                               |

Exactly one of `rotation` or `quaternion` must be present.

#### 9.4 `keypoints`

Named landmarks with per-point visibility (pose estimation, facial landmarks). Unlike COCO's positional `[x, y, v, x, y, v, …]` flat array, JAMESON keys observations by landmark **name**, so a value is meaningful without counting offsets — but the definition still fixes the canonical landmark set.

The field **definition** declares the landmark roster and optional skeleton:

```json
{
  "id": 7,
  "name": "body_pose",
  "label": "Body Pose",
  "type": "keypoints",
  "points": [
    { "name": "nose", "label": "Nose" },
    { "name": "left_shoulder", "label": "Left Shoulder" },
    { "name": "right_shoulder", "label": "Right Shoulder" }
  ],
  "skeleton": [ ["left_shoulder", "right_shoulder"], ["nose", "left_shoulder"] ]
}
```

- `points`: ordered array of `{ name, label?, description? }`; `name` unique within the field. Order is the rendering/legend order.
- `skeleton` (optional): array of `[nameA, nameB]` pairs declaring connectivity for rendering. Both names must appear in `points`.

The **value** maps landmark names to observations. Landmarks may be omitted (unobserved):

```json
{
  "nose": { "position": [412, 220], "visibility": "visible" },
  "left_shoulder": { "position": [380, 300], "visibility": "occluded" }
}
```

| Field        | Type                       | Required | Description                                        |
| ------------ | -------------------------- | -------- | -------------------------------------------------- |
| `position`   | array of 2 or 3 numbers    | yes      | Same coordinate conventions as `point`             |
| `visibility` | string                     | no       | `"visible"` (default), `"occluded"` (position estimated), `"absent"` (landmark does not exist on this instance; `position` ignored) |

#### 9.5 `mask`

A raster segmentation mask, stored as COCO-compatible run-length encoding so existing RLE tooling applies directly:

```json
{
  "size": [1080, 1920],
  "counts": [0, 240, 15, 1665, 18, 1662, 21, ...]
}
```

- `size`: `[height, width]` in pixels (COCO order).
- `counts`: uncompressed COCO RLE — alternating run lengths of 0s and 1s in column-major (Fortran) order, beginning with the count of 0s.

Compressed (string-encoded) RLE is not part of v0.4; producers must emit the uncompressed array form.

#### 9.6 Unknown types

Unknown field types must be treated as `json` for forward compatibility (value preserved, not rendered). Producers must only emit registered types or `x-` prefixed experimental types.

---

### 10. Conditional Visibility (`visible_when`)

A field definition may carry a `visible_when` clause: the field is shown — and its `required` flag enforced — only while the condition holds.

```json
"visible_when": {
  "field_name": "damage_type",
  "operator": "in",
  "values": ["dent", "missing"]
}
```

| Field      | Type             | Required | Description                                            |
| ---------- | ---------------- | -------- | ------------------------------------------------------ |
| `field_name` | string         | yes      | `name` of the trigger field                            |
| `operator` | string           | yes      | One of the operators below                             |
| `values`   | array of strings | operator-dependent | Present iff operator is `equals` / `in` / `contains_any` |

| Operator       | Trigger field types                | Condition holds when…                                  |
| -------------- | ---------------------------------- | ------------------------------------------------------ |
| `equals`       | `single_select`, `text`, `url`, `date` | trigger's answer equals `values[0]`                |
| `in`           | `single_select`, `text`, `url`, `date` | trigger's answer is one of `values`                |
| `contains_any` | `multi_select`, `cascading_select` | trigger's answer array intersects `values`             |
| `is_true`      | `boolean`                          | trigger's answer is `true`                             |
| `is_false`     | `boolean`                          | trigger's answer is `false`                            |
| `is_answered`  | any                                | trigger has any non-empty answer                       |

#### 10.1 Forward references only (normative)

`visible_when.field_name` must name a definition at a **strictly smaller index** in `fields`. This guarantees the dependency graph is acyclic and lets forms be evaluated in a single top-to-bottom pass.

#### 10.2 Semantics (normative)

- A field is **visible** iff it has no `visible_when`, or its condition holds **and its trigger field is itself visible** (visibility chains).
- A hidden field is not rendered, its `required` flag is not enforced, and producers should omit its value from annotations.
- Validators enforcing `required` (§16 rule 5) must evaluate visibility first: a missing value for a hidden required field is **not** an error. A naive always-on `required` check will reject valid files.

Compound conditions (`all_of` / `any_of`) are reserved for a future minor version; v0.4 conditions are a single clause by design.

---

### 11. `categories` Array (optional)

Used for primary semantic classes (the COCO-style "what kind of thing is this?"). Categories complement fields: `category_id` answers *what the part is*; field values answer *everything else about it*.

```json
{
  "id": 1,
  "name": "wheel",
  "label": "Wheel",
  "supercategory": "vehicle_part",
  "color": "#7ED321",
  "extra": {}
}
```

| Field           | Type    | Required | Description                 |
| --------------- | ------- | -------- | --------------------------- |
| `id`            | integer | yes      | Unique positive integer     |
| `name`          | string  | yes      | Stable machine name         |
| `label`         | string  | no       | Display name (defaults to `name`) |
| `supercategory` | string  | no       | Higher-level grouping       |
| `color`         | string  | no       | Hex color for visualization |
| `extra`         | object  | no       |                             |

May be an empty array when categories are not used.

---

### 12. `annotations` Array

Each annotation links a part (and optionally a category) to a set of field values.

```json
{
  "id": 1001,
  "part_id": 101,
  "category_id": 1,
  "values": [
    { "field_id": 1, "value": [120.5, 340.0, 80.0, 45.5] },
    { "field_id": 2, "value": true },
    { "field_id": 3, "value": "Slight occlusion on left side" }
  ],
  "provenance": null,
  "extra": {}
}
```

| Field         | Type    | Required | Description                               |
| ------------- | ------- | -------- | ----------------------------------------- |
| `id`          | integer | yes      | Unique positive integer                   |
| `part_id`     | integer | yes      | References `parts[].id`                   |
| `category_id` | integer | no       | References `categories[].id`              |
| `values`      | array   | yes      | List of `{ field_id, value }` objects |
| `provenance`  | object  | no       | Who/what produced this annotation (§12.2) |
| `extra`       | object  | no       |                                           |

**Value rules**

- `field_id` must reference an entry in `fields`.
- `value` must match the shape defined by its field's `type` and satisfy its `constraints` and options/taxonomy.
- The same `field_id` must not appear more than once in a single annotation's `values`.

#### 12.1 Geometry rule (normative)

**A part has at most one geometry-defining annotation, and multiple geometric instances mean multiple `region` parts.**

- A drawn instance (2D box, polygon, point, mask, pose, 3D cuboid) is a part with `type: "region"`, structurally contained via `parent_part_id` in whatever it was drawn on: the `file` part of an image, a `frame` part of a video, a `mesh` part of a 3D asset.
- The region part's single annotation carries exactly one geometry value (a value of a `bbox`, `rotated_bbox`, `polygon`, `polyline`, `point`, `keypoints`, `mask`, or `bbox3d` field), which **defines the part's extent**, plus any number of form values describing it.
- Three damage cuboids on one mesh = three `region` parts under that mesh part, each with its own annotation, category, and (if tracked) `track_id`.
- Non-region parts (`file`, `mesh`, `row`, `frame`, `track`, `segment`, `page`, `span`) must not carry geometry values.

This single rule covers every modality uniformly: an image bounding box is simply a `region` under a `file` part — the degenerate single-frame case of the video model in §14.

#### 12.2 `provenance` and multiplicity

By default, consumers may assume **at most one annotation per part** — the document represents one resolved set of answers (e.g. reviewed/accepted labels). Producers exporting multiple opinions (several labelers, model prelabels alongside human labels) must distinguish them via `provenance`:

```json
"provenance": {
  "source": "human",
  "author": "labeler-42",
  "role": "labeler",
  "created_at": "2026-08-15T16:20:00Z"
}
```

| Field        | Type   | Description                                          |
| ------------ | ------ | ---------------------------------------------------- |
| `source`     | string  | Kind of agent that produced the annotation: `"human"`, `"model"`, `"consensus"` (computed by agreement rules, no single author), … |
| `author`     | string  | Opaque author identifier                             |
| `role`       | string  | e.g. `"labeler"`, `"reviewer"`                       |
| `created_at` | string  | ISO 8601 datetime                                    |
| `resolved`   | boolean | `true` marks the producer's resolved answers for this part (resolved-set convention below); absent means `false` |

Multiple annotations on the same part are legal only if they differ in `provenance`. Two annotations with identical (or absent) provenance on one part make the document invalid — there would be no way to know which is authoritative.

**Resolved-set convention (non-normative).** JAMESON itself never designates one annotation as authoritative — resolution policy belongs to whoever reads the document. A producer exporting multiple opinions SHOULD therefore also include its own resolved answers as one additional annotation per part, flagged `resolved: true`. The resolved annotation's `source` still describes what produced it: `source: "human", role: "reviewer"` when a reviewer signed off on the answers, `source: "consensus"` when they were computed by agreement rules with no human sign-off. Consumers that do not want to adjudicate take the `resolved: true` annotation and ignore the rest; consumers with their own policy filter to the unresolved opinions and resolve them however they choose — most recent `created_at`, majority vote, or a review pass of their own. To make timestamp-based policies possible, producers emitting multiple opinions SHOULD set `created_at` on every annotation.

Note that a reviewer's raw opinion and a reviewer-signed resolved annotation may share `source`, `author`, and `role`; they remain distinct provenance because they differ in `resolved` (and normally `created_at`), so the multiplicity rule above is satisfied.

Two clarifications for multi-opinion documents:

- **Geometry stays unique.** The geometry rule (§12.1) is unchanged: a region part still has exactly one geometry-defining annotation. When several opinions attach to one region part, exactly one of them (by preference the resolved annotation) carries the geometry value; the other opinions on that part carry form values only. Distinct drawn instances remain distinct region parts, never competing annotations on one part.
- **Authors are opaque.** `author` is an opaque identifier by design. Producers SHOULD prefer stable non-personal identifiers (e.g. UUIDs) over personal data such as email addresses — annotation documents routinely travel beyond the labeling platform that produced them.

---

### 13. Ontology Documents

A JAMESON document may carry **only** an ontology: `fields` (and optionally `categories`) populated, with `files`, `parts`, and `annotations` empty. This makes JAMESON a schema-interchange format as well as an annotation format — an ontology can be authored anywhere, uploaded into a labeling tool, and rendered as a working form with no other input.

```json
{
  "jameson_version": "0.4",
  "info": {
    "ontology": { "name": "vehicle-damage-qa", "version": 1 }
  },
  "files": [],
  "parts": [],
  "fields": [
    { "id": 1, "name": "is_damaged", "label": "Is Damaged?", "type": "boolean", "required": true },
    {
      "id": 2, "name": "damage_type", "label": "Damage Type", "type": "single_select",
      "required": true, "render": "radio",
      "options": [
        { "value": "scratch", "label": "Scratch" },
        { "value": "dent", "label": "Dent" }
      ],
      "visible_when": { "field_name": "is_damaged", "operator": "is_true" }
    },
    { "id": 3, "name": "notes", "label": "Notes", "type": "text", "render": "textarea",
      "constraints": { "max_length": 2000 } }
  ],
  "categories": [],
  "annotations": []
}
```

Rules for ontology documents:

- `info.ontology.name` is recommended so imports are idempotent and versionable.
- All of §8 and §10 apply: field order is form order, `visible_when` references must be forward-only, per-type fields (`options`, `levels`/`taxonomy`) must be present and valid.
- An importer must be able to reconstruct the complete form UI from the document alone — that property is the acceptance test for both this section and any importer implementation.
- Geometry-typed fields (`bbox`, `rotated_bbox`, `polygon`, `polyline`, `point`, `keypoints`, `mask`, `bbox3d`) are legal in an ontology document: they declare which drawing tools a task offers, and for `keypoints` they carry the landmark roster and skeleton. An importer that does not yet support a declared geometry type must reject the import (or disable those tools) rather than silently drop the definitions.

---

### 14. Video Conventions

JAMESON models video with the same three concepts used everywhere else — containment (`parent_part_id`), located parts (`locator`), and identity (`track_id`) — rather than a special-purpose track structure. This is the gap in COCO this spec set out to close: COCO can label frames, but has no defined way to say "this box in frame 42 and that box in frame 43 are the same car."

#### 14.1 Structure

- One `files` entry represents the video (with `fps`, `frame_count`, `duration_seconds` when known).
- Each annotated frame is **one canonical `frame` part** — `locator: { frame_index, timestamp }`, at most one per `(file_id, frame_index)`. Frame-level annotations ("frame is blurry") attach here.
- Each object appearance is a **`region` part** whose `parent_part_id` is the frame part and whose annotation carries the geometry (§12.1).
- Each object identity is a **`track` part** (no locator). Region parts belonging to it set `track_id` to its id.

```
file (video)
frame[42] ── region (bbox, track_id → car_track_07)
         └─ region (bbox, track_id → car_track_08)
frame[43] ── region (bbox, track_id → car_track_07)
track: car_track_07   (annotation: category "car", identity values)
track: car_track_08
```

Note frames are *not* children of tracks: a part has one parent, and a frame containing two objects must serve both tracks. The containment tree stays structural; identity is the `track_id` cross-link.

#### 14.2 Value placement rule (normative)

- **Identity-level values** — the category ("this is a car"), license plate, color — annotate the **track part**, once. They must not be repeated per frame, where copies could disagree.
- **Per-frame state** — geometry, occluded, truncated, blurred — annotates the **region parts**.

#### 14.3 Keyframes and interpolation

Labeling only keyframes is the norm. A region part may set the defined field `keyframe: true` (§6), meaning intermediate frames between consecutive keyframe regions of the same track may be linearly interpolated by consumers. Absent the flag (or `false`), regions are literal observations and no interpolation is implied.

Whether interpolation is licensed changes what a consumer renders, so per the rigidity principle (§2) this flag is a defined part field, never `extra` metadata. (Drafts prior to this revision carried it as `extra.keyframe`; consumers may accept that legacy form, but producers must emit the defined field.)

#### 14.4 Temporal segments

Actions and events spanning time are `segment` parts (`locator` with `start_frame`/`end_frame` and/or `start_time`/`end_time`; frame fields authoritative). A segment may carry `track_id` to scope it to one object — "car_track_07 is occluded from frame 120–185" — or omit it to describe the whole video.

```json
{
  "id": 300,
  "file_id": 1,
  "type": "segment",
  "name": "occluded_span",
  "track_id": 200,
  "locator": { "start_frame": 120, "end_frame": 185 }
}
```

#### 14.5 Worked example — two cars, two frames

```json
{
  "jameson_version": "0.4",
  "info": { "description": "Traffic MOT sample" },
  "files": [
    { "id": 1, "file_name": "traffic_001.mp4", "file_type": "mp4",
      "width": 1920, "height": 1080, "fps": 30.0, "frame_count": 900 }
  ],
  "parts": [
    { "id": 200, "file_id": 1, "type": "track", "name": "car_track_07" },
    { "id": 201, "file_id": 1, "type": "track", "name": "car_track_08" },

    { "id": 1001, "file_id": 1, "type": "frame", "locator": { "frame_index": 42, "timestamp": 1.4 } },
    { "id": 1002, "file_id": 1, "type": "frame", "locator": { "frame_index": 43, "timestamp": 1.433 } },

    { "id": 1101, "file_id": 1, "type": "region", "parent_part_id": 1001, "track_id": 200 },
    { "id": 1102, "file_id": 1, "type": "region", "parent_part_id": 1001, "track_id": 201 },
    { "id": 1103, "file_id": 1, "type": "region", "parent_part_id": 1002, "track_id": 200,
      "keyframe": true }
  ],
  "fields": [
    { "id": 1, "name": "bbox", "label": "Bounding Box", "type": "bbox" },
    { "id": 2, "name": "occluded", "label": "Occluded", "type": "boolean" },
    { "id": 3, "name": "license_plate", "label": "License Plate", "type": "text" }
  ],
  "categories": [
    { "id": 1, "name": "car", "supercategory": "vehicle" }
  ],
  "annotations": [
    { "id": 9000, "part_id": 200, "category_id": 1,
      "values": [ { "field_id": 3, "value": "7ABC123" } ] },
    { "id": 9001, "part_id": 201, "category_id": 1, "values": [] },

    { "id": 9101, "part_id": 1101,
      "values": [ { "field_id": 1, "value": [320, 480, 210, 130] },
                      { "field_id": 2, "value": false } ] },
    { "id": 9102, "part_id": 1102,
      "values": [ { "field_id": 1, "value": [900, 460, 180, 120] },
                      { "field_id": 2, "value": true } ] },
    { "id": 9103, "part_id": 1103,
      "values": [ { "field_id": 1, "value": [335, 482, 212, 131] },
                      { "field_id": 2, "value": false } ] }
  ]
}
```

#### 14.6 Audio Conventions

Audio labeling (speech transcription, diarization, sound-event detection) uses the same primitives as video — no audio-specific structure exists or is needed:

- The audio file is a `files` entry (`file_type: "wav"`, `duration_seconds`; `fps`/`frame_count`/`width`/`height` omitted).
- Every labeled span — an utterance, a word, a sound event — is a **`segment` part** with `locator: { start_time, end_time }` in seconds. The transcript and any other answers are ordinary field values on the segment's annotation.
- **Segments may contain segments** (`parent_part_id`): utterance segments containing word segments is the canonical transcription structure (equivalent to tiered interval formats such as Praat TextGrids). A child segment's time range must lie within its parent's.
- **Speaker diarization is `track_id`**: each speaker is a `track` part; utterance and word segments carry `track_id`. Speaker-level values (name, accent, role) annotate the track once, per the placement rule in §14.2 — exactly as a car's identity persists across video frames.
- Multi-channel audio: a `channel` part type is a registry candidate (§7); until it is registered, producers needing per-channel scoping must use an `x-` type.

Example — word-level transcription with two speakers:

```json
"parts": [
  { "id": 10,  "file_id": 1, "type": "track", "name": "speaker_A" },
  { "id": 11,  "file_id": 1, "type": "track", "name": "speaker_B" },
  { "id": 100, "file_id": 1, "type": "segment", "track_id": 10,
    "locator": { "start_time": 4.02, "end_time": 6.85 } },
  { "id": 101, "file_id": 1, "type": "segment", "parent_part_id": 100, "track_id": 10,
    "locator": { "start_time": 4.02, "end_time": 4.31 } },
  { "id": 102, "file_id": 1, "type": "segment", "parent_part_id": 100, "track_id": 10,
    "locator": { "start_time": 4.35, "end_time": 4.62 } }
],
"annotations": [
  { "id": 900, "part_id": 100, "values": [ { "field_id": 1, "value": "turn left at the light" } ] },
  { "id": 901, "part_id": 101, "values": [ { "field_id": 1, "value": "turn" } ] },
  { "id": 902, "part_id": 102, "values": [ { "field_id": 1, "value": "left" } ] }
]
```

#### 14.7 Text Conventions

Character-span labeling (named-entity recognition, sentence and clause structure, coreference) uses the same primitives — the `span` part type is the only text-specific concept:

- The text document is a `files` entry (e.g. `file_type: "txt"`). Offsets index the file's decoded text as a sequence of Unicode code points, zero-based and end-exclusive (§7).
- Every labeled range is a **`span` part** with `locator: { start_char, end_char }`. The entity type and any other answers are ordinary field values on the span's annotation.
- **Spans may contain spans** (`parent_part_id`): sentence spans containing entity spans, quotations containing speech. A child span's range must lie within its parent's.
- **Coreference is `track_id`**: mentions of the same real-world entity are spans sharing a `track` part — exactly as a car's identity persists across video frames. Entity-level values (canonical name, entity class) annotate the track once, per the placement rule in §14.2; mention-level values (surface form, pronoun vs. proper noun) annotate the spans.
- `span` addresses natural text files. Labeling text *extracted* from visual documents (PDF OCR) is out of scope for `span` — draw `region` parts on `page` parts instead (§7).

Example — NER with coreference (text begins `"Dr. Chen …"`, a later sentence begins `"She …"`):

```json
"parts": [
  { "id": 10,  "file_id": 1, "type": "track", "name": "entity_chen" },
  { "id": 100, "file_id": 1, "type": "span", "track_id": 10,
    "locator": { "start_char": 0, "end_char": 8 } },
  { "id": 101, "file_id": 1, "type": "span", "track_id": 10,
    "locator": { "start_char": 42, "end_char": 45 } }
],
"annotations": [
  { "id": 900, "part_id": 10,  "values": [ { "field_id": 2, "value": "person" } ] },
  { "id": 901, "part_id": 100, "values": [ { "field_id": 1, "value": "proper" } ] },
  { "id": 902, "part_id": 101, "values": [ { "field_id": 1, "value": "pronoun" } ] }
]
```

---

### 15. Additional Examples

#### 15.1 Image + bounding box (region-part model)

```json
{
  "jameson_version": "0.4",
  "info": { "description": "Parking lot vehicle detection" },
  "files": [
    { "id": 1, "file_name": "parking_lot_001.jpg", "file_type": "jpg",
      "width": 1920, "height": 1080 }
  ],
  "parts": [
    { "id": 100, "file_id": 1, "type": "file", "name": "parking_lot_001" },
    { "id": 101, "file_id": 1, "type": "region", "name": "vehicle_1", "parent_part_id": 100 }
  ],
  "fields": [
    { "id": 1, "name": "bbox", "label": "Bounding Box", "type": "bbox" },
    { "id": 2, "name": "occluded", "label": "Occluded", "type": "boolean" }
  ],
  "categories": [
    { "id": 1, "name": "car", "supercategory": "vehicle" },
    { "id": 2, "name": "truck", "supercategory": "vehicle" }
  ],
  "annotations": [
    { "id": 1001, "part_id": 101, "category_id": 1,
      "values": [ { "field_id": 1, "value": [320, 480, 210, 130] },
                      { "field_id": 2, "value": false } ] }
  ]
}
```

#### 15.2 Multi-mesh GLB with quality ontology

```json
{
  "jameson_version": "0.4",
  "info": {
    "description": "GLB quality review",
    "contributor": "MLtwist",
    "ontology": { "name": "glb-quality-review", "version": 7 }
  },
  "files": [
    { "id": 1, "file_name": "car_001.glb", "file_type": "glb",
      "source_id": "8f14e45f-ceea-4e2b-9c5d-0d1b2f3a4c5e",
      "extra": { "num_meshes": 8 } }
  ],
  "parts": [
    { "id": 100, "file_id": 1, "type": "file", "name": "car_001" },
    { "id": 101, "file_id": 1, "type": "mesh", "name": "Body",
      "parent_part_id": 100, "locator": { "node_path": "Root/Body[0]" } },
    { "id": 102, "file_id": 1, "type": "mesh", "name": "Wheel_FL",
      "parent_part_id": 101, "locator": { "node_path": "Root/Body[0]/Wheel_FL[3]" } },
    { "id": 103, "file_id": 1, "type": "region", "name": "dent_1",
      "parent_part_id": 101 }
  ],
  "fields": [
    { "id": 1, "name": "is_quality_good", "label": "Quality OK?", "type": "boolean", "required": true },
    { "id": 2, "name": "notes", "label": "Notes", "type": "text", "render": "textarea" },
    { "id": 3, "name": "damage_bounds", "label": "Damage Bounds", "type": "bbox3d" }
  ],
  "categories": [],
  "annotations": [
    { "id": 1001, "part_id": 100,
      "values": [ { "field_id": 1, "value": true } ] },
    { "id": 1002, "part_id": 102,
      "values": [ { "field_id": 1, "value": false },
                      { "field_id": 2, "value": "Missing geometry" } ] },
    { "id": 1003, "part_id": 103,
      "values": [ { "field_id": 3, "value": {
          "center": [0.4, 0.9, -0.2],
          "size": [0.3, 0.2, 0.1],
          "rotation": [0.0, 0.0, 0.0]
        } } ] }
  ]
}
```

#### 15.3 Spreadsheet row labeling

```json
{
  "jameson_version": "0.4",
  "info": { "description": "Invoice row classification" },
  "files": [
    { "id": 1, "file_name": "invoices_q3.xlsx", "file_type": "xlsx" }
  ],
  "parts": [
    { "id": 501, "file_id": 1, "type": "row", "name": "row_42",
      "locator": { "sheet": "Sheet1", "row_index": 42 } }
  ],
  "fields": [
    { "id": 1, "name": "document_type", "label": "Document Type", "type": "single_select",
      "required": true,
      "options": [
        { "value": "invoice", "label": "Invoice" },
        { "value": "receipt", "label": "Receipt" },
        { "value": "credit_note", "label": "Credit Note" }
      ] },
    { "id": 2, "name": "risk_level", "label": "Risk Level", "type": "single_select",
      "render": "radio",
      "options": [
        { "value": "low", "label": "Low" },
        { "value": "medium", "label": "Medium" },
        { "value": "high", "label": "High" }
      ] },
    { "id": 3, "name": "notes", "label": "Notes", "type": "text" }
  ],
  "categories": [],
  "annotations": [
    { "id": 5001, "part_id": 501,
      "values": [ { "field_id": 1, "value": "invoice" },
                      { "field_id": 2, "value": "high" },
                      { "field_id": 3, "value": "Missing PO number" } ] }
  ]
}
```

---

### 16. Validation

Implementations should enforce, in addition to the shapes above:

1. **Referential integrity**: every `file_id`, `part_id`, `parent_part_id`, `track_id`, `category_id`, `field_id`, and `visible_when.field_name` references an existing entry.
2. **Unique ids** within each array; unique `name` within `fields`; unique option `value`s within a field; unique taxonomy `value`s among siblings; unique landmark `name`s within a `keypoints` roster, with `skeleton` pairs referencing only rostered names.
3. **Part typing**: `type` is registered or `x-` prefixed; `locator` matches the type's required shape (§7); at most one `file` part per file; at most one `frame` part per `(file_id, frame_index)`; `keyframe` appears only on `region` parts.
4. **Tree soundness**: `parent_part_id` forms a forest (no cycles); a child references a part with the same `file_id`; where parent and child both carry `node_path`, the child's path extends the parent's; a `segment` child of a `segment` lies within its parent's time range; a `span` child of a `span` lies within its parent's character range.
5. **Identity links**: `track_id` references a part with `type: "track"` and the same `file_id`; `track` parts do not themselves carry `track_id`.
6. **Value validity**: every `value` matches its definition's `type` shape, `constraints`, options, or taxonomy path; `keypoints` values use only rostered landmark names; no duplicate `field_id` within an annotation.
7. **Geometry rule**: geometry values appear only on annotations of `region` parts; each region part's annotation carries exactly one geometry value (§12.1).
8. **Conditional requiredness**: `required` is enforced only for fields visible under §10.2; `visible_when` references are forward-only (§10.1).
9. **Multiplicity**: multiple annotations on one part differ in `provenance` (§12.2).
10. **Ontology well-formedness**: constraint sets satisfy §8.6 — legal keys for the type, coherent (non-empty) ranges, integer coherence, safe-subset compilable `pattern`, self-contained draft-2020-12 `json_schema`. Documents failing these are rejected at import, before any rendering or labeling.

A JSON Schema for JAMESON v0.4 will be published alongside this specification. (JSON Schema cannot express rules 4, 7, 8, and 9 — reference validators must implement them in code.)

---

### 17. Versioning & Compatibility

- The current version is `"0.4"`.
- Minor version increments may add optional fields, part types, field types, string formats, and render hints. Current registry candidates: part types `paragraph`, `channel` (audio), `slice` (medical volumes); field types `datetime`, `range` (an interval as the *answer*, distinct from min/max constraints on a scalar); polygon holes / multi-polygon; geometry type `point_indices` (point-cloud instance segmentation as arrays of point indices, for LiDAR); a declared coordinate space (e.g. geospatial WGS84) as an alternative to the pixel and asset-scene frames of §9.2.
- Major version increments may introduce breaking changes.
- Consumers must ignore unknown top-level keys and unknown fields, treat unknown field types as `json`, and preserve (without rendering) parts of unknown type.

#### Changelog

**v0.4 (2026-08-20)**

- **Provenance `resolved` flag (§12.2)**: new optional boolean marking the producer's resolved answers for a part. `source` now describes only the kind of agent that produced the annotation (`"human"`, `"model"`, `"consensus"`); the former `"review"` source is retired — a reviewer-signed resolution is `source: "human", role: "reviewer", resolved: true`.
- **Resolved-set convention (§12.2, non-normative)**: documents carrying multiple opinions per part SHOULD also include the producer's resolved answers as a `resolved: true` annotation. Consumers that do not adjudicate take that annotation; all others filter the unresolved opinions and apply their own policy (e.g. most recent `created_at`). Made explicit that the format itself never designates an annotation as authoritative.
- **Multi-opinion clarifications (§12.2)**: the geometry rule (§12.1) is unchanged under multiple opinions — one geometry-defining annotation per region part, by preference the resolved one; producers SHOULD set `created_at` on every annotation in multi-opinion documents; producers SHOULD use stable non-personal `author` identifiers (e.g. UUIDs) rather than emails.
- Additive in practice: `resolved` is optional and `source` is an open registry, so v0.3 documents remain readable; producers using `source: "review"` should migrate to `source: "human", role: "reviewer", resolved: true`.

**v0.3 (2026-08-15)**

- **Naming**: `attribute_definitions` renamed to `fields`, annotation `attributes` renamed to `values` (entries are `{ field_id, value }`), `attribute_id` renamed to `field_id`, and `visible_when.field` renamed to `field_name` (it references a field by name, not id). Every id-valued reference key now follows `<array>_id` naming.
- **Constraint enforcement contract (§8.6)**: the three-point model (validate at import, honor at render, re-validate at submit); normative list of ill-formed constraint sets importers must reject; untrusted-ontology rules (`pattern` limited to a linear-time-safe / RE2-compatible subset, `json_schema` pinned to draft 2020-12 with remote `$ref` forbidden); no-defaults and no-expression-language declared as deliberate non-features.
- **Number constraints completed (§8.3)**: added `exclusive_min` / `exclusive_max`; defined step anchoring (`min + k*step`, decimal evaluation — `0.3` satisfies `step: 0.1`), integer coherence, and IEEE-double precision guidance (currency and >2^53 identifiers use `text`). A single `number` type with constraints is retained deliberately — no `int`/`float` split, since JSON has one number type and the type/constraint/render separation is the spec's core discipline.
- **Named string formats (§8.3.1)**: `format` registry (`email`, `phone_e164`, `uuid`, `hostname`, `ipv4`/`ipv6`) preferred over producer-authored patterns.
- **Geometry precision**: `rotated_bbox` theta direction defined exactly (positive x-axis toward positive y-axis in the y-down frame); normalized (0–1) coordinates declared non-conforming.
- **Audio conventions (§14.6)**: transcription via nested `segment` parts (utterance → word), diarization via `track_id`, worked example; `channel` remains a registry candidate.
- **Text spans (§7, §14.7)**: new `span` part type — zero-based, end-exclusive **Unicode code point** ranges into a text file's decoded content — covering NER, sentence structure (nested spans), and entity coreference (`track_id` across mentions).
- **`keyframe` promoted to a defined part field (§6, §14.3)**: interpolation eligibility affects rendering, so per the rigidity principle it cannot live in `extra`; the legacy `extra.keyframe` form is readable but deprecated.
- **Registry candidates (§17)**: geometry type `point_indices` (point-cloud index segmentation) and declared coordinate spaces (geospatial WGS84), added after a comparative review of Dataloop's export formats.
- Validation: added rule 10 (ontology well-formedness at import), nested-segment time containment and nested-span range containment to rule 4, and `keyframe`-only-on-regions to rule 3.

**v0.2 (2026-08-15)**

- `parts.type` is now **required** and governed by a registry (§7) with per-type normative `locator` shapes; part identity no longer lives in `extra`.
- Added `locator` object to parts; defined `node_path` formation, zero-based indexing, and escaping rules.
- Added `track_id` cross-link for object identity; **rewrote video conventions (§14)**: canonical frame parts, region parts under frames, identity on track parts. Replaces the v0.1 frame-under-track model, which could not represent two objects in one frame.
- Added the **geometry rule** (§12.1): geometry lives on `region` parts, one geometry-defining annotation per part; multiple instances = multiple region parts. Resolves v0.1's ambiguity where a part's extent was defined by an arbitrary annotation.
- **Ontology overhaul (§8, §10)**: options are `{value, label}` objects; added `label`, `constraints`, `render` hints, cascading `levels`/`taxonomy`/`require_full_path`, and `visible_when` conditional visibility with forward-reference and conditional-required semantics.
- **Geometry types expanded (§9)**: added `rotated_bbox`, `polyline`, `keypoints` (named landmarks with visibility + skeleton), and `mask` (uncompressed COCO RLE). All geometry types are first-class ontology field types — an ontology document may declare them as drawing tools even if a given labeling tool does not support them yet.
- Added **ontology documents** (§13): a JAMESON file may carry only an ontology, for schema interchange and labeling-tool import.
- `bbox3d` tightened: exactly one of Euler `rotation` (radians, intrinsic X-Y-Z) or `quaternion`; corner-point representation explicitly rejected.
- Defined normative 2D (top-left pixel) and 3D (asset scene space; glTF: right-handed, +Y up, meters) coordinate frames.
- `files`: added `source_id`, `uri`, `fps`, `frame_count`, `duration_seconds`; `file_type` normalized to lowercase extension; clarified one entry per logical asset.
- `annotations`: added `provenance` and the multiplicity rule (default one annotation per part).
- `info`: added `ontology` provenance object and `extra`.
- Expanded validation requirements (§16).

**v0.1 (2026-08-15)** — initial draft.

---

### 18. License

This specification is released under the Creative Commons Attribution 4.0 International License (CC-BY-4.0).

---

**End of JAMESON Annotation Format Specification Draft v0.4**
