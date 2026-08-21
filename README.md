# JAMESON Annotation Format

**JAMESON** — **J**SON **A**nnotation **M**odel with **E**mbedded **S**chema and **O**ntology **N**otation — is a general-purpose JSON format for multi-modal data labeling: annotations *and* the ontologies that define them, in one self-describing document.

## History

JAMESON was created by Brice Ayres at [MLtwist](https://mltwist.com). The name is a triple tribute: it honors his son, Jameson; it's a play on **JSON** — the file format every JAMESON document is written in; and it expands to an accurate description of the format itself, *JSON Annotation Model with Embedded Schema and Ontology Notation*. It is styled in capitals as an acronym, following the convention of the format it succeeds (COCO, *Common Objects in Context*). The name is intentional and permanent.

The format was born out of real delivery pain, not abstract standards work. MLtwist's video clients wanted their annotations in COCO — the lingua franca of computer vision — but COCO couldn't express what they actually needed. There is no defined way in COCO to say that a bounding box in one frame and a bounding box in the next frame are *the same car*: people label frames as if they were independent images, and object identity across time is left to ad-hoc convention. So MLtwist did what everyone does — built a modified "COCO Plus" format. And like everyone's COCO Plus, it drifted: each client's variant was a little different, and every new engagement meant re-negotiating the dialect.

Then came clients labeling 3D assets — multi-mesh GLB files where annotations attach to individual meshes, not to the file as a whole: a single car model might carry separate meshes for the hood, the doors, the windshield, and each of its four wheels, every one of them labeled independently — and spreadsheets where each row is the labeled unit. COCO has no concept of a labelable *sub-unit* of a file at all, so no amount of patching would converge. Rather than mint a third and fourth one-off dialect, Brice designed a single universal format built around that missing concept, covering:

- **Images** — boxes, rotated boxes, polygons, points, keypoints/pose, masks
- **Video** — frame-level labels, multi-object tracking with true cross-frame identity, temporal segments
- **Audio** — transcription, speaker diarization, sound events
- **Text** — character-span labeling: named-entity recognition, sentence structure, coreference
- **3D assets** — multi-mesh GLB/glTF scene graphs, 3D cuboids, point clouds
- **Spreadsheets and tabular data** — rows as labelable units
- **Documents and PDFs** — pages and regions on pages
- **Whole-file classification and QA** — for any file type

— with governed extension points for the modalities that come next, so supporting a new data type never again means forking the format.

## Core principles

Every design decision in the spec traces back to one of these:

1. **Rigid where it matters.** Two independent teams on the same JAMESON version must be able to exchange documents without a conversation. So the spec defines exactly **one way to express each thing**: anything a consumer must read to locate, validate, or render an annotation is a defined field with a normative shape — never free-form metadata, never a choice between equivalent representations. Formats that offer a concept flexible enough to mean several different things force every consumer to implement — and guess between — all of the meanings; that flexibility is precisely what makes two conforming producers mutually unreadable, and JAMESON rejects it. Where producers genuinely need room to experiment, the escape hatch is governed: `x-` prefixed registry values, which consumers may safely ignore.

2. **Extensible without breakage.** Within a major version, the spec only ever *adds*: optional fields, and new entries in the governed registries (part types, field types, string formats, render hints). Consumers must ignore unknown fields and preserve unknown types, so a v0.3 document remains valid and readable under every later v0.x spec, and new modalities and use cases arrive as registry entries — never as forks. Proven `x-` experiments are promoted into the registries by minor versions.

3. **Self-contained.** A JAMESON document alone is enough to parse, validate, and render everything in it: the ontology travels inside the file, and nothing references a remote resource a validator would have to fetch. There is no out-of-band schema, recipe, or platform to consult.

4. **Few primitives, every modality.** New data types get new *part types*, not new structures. The same three mechanisms — typed located parts, structural containment, and track identity — model object tracking in video, speaker diarization in audio, and entity coreference in text. One format for all labeling projects means learning the model once, not per modality.

5. **Compact and readable.** Documents are meant to be read by humans as well as machines: short, unambiguous key names; every reference key uniformly shaped as `<array>_id`; and a declare-once, reference-everywhere structure — a field's type, options, and constraints appear one time in `fields`, and ten thousand annotations reference it by id rather than repeating it. Verbosity that inflates file size without adding information is treated as a defect.

6. **Standards over invention.** Where a sound convention already exists, JAMESON adopts it rather than minting its own: ISO 8601 dates and times, COCO's `[x, y, width, height]` boxes and RLE masks, the center/size/rotation cuboid used by the major 3D driving datasets, glTF's coordinate space for 3D assets, JSON Schema draft 2020-12, RFC-defined string formats, and linear-time-safe (RE2-class) regular expressions. Invention is reserved for the gaps this format exists to fill.

7. **No silent semantics.** Nothing in a document means something a reader can't see, and nothing is manufactured on a labeler's behalf: there are no default values (an absent answer means *never answered*, not an assumed one), no implicit state that must be replayed to know what's true, and no constraint that validates differently in two implementations. Ill-formed documents fail loudly at import — in front of the ontology author — never silently in front of a labeler or, worse, downstream in training data.

## Why not COCO?

It follows the spirit of COCO (multiple files in one document, explicit objects, linked annotations) while fixing COCO's two structural gaps:

1. **COCO has no concept of a labelable sub-unit of a file.** A mesh inside a GLB, a row in a spreadsheet, a frame in a video, the same car tracked across frames — none of these are addressable. JAMESON makes every labelable unit a first-class **part** with a typed, normative locator into its source file.
2. **COCO carries no ontology.** Its `categories` list is its entire schema; attribute dictionaries have no declared types, options, or constraints, so attribute-rich COCO files do not interoperate. JAMESON embeds a formal **fields** system — typed form fields, select options with display labels, cascading taxonomies, validation constraints, conditional visibility — so a consumer can render the complete labeling form and validate every value from the document alone.

## Core model

```
files                  one entry per logical source asset
 └── parts             every labelable unit: file, mesh, row, frame, track, segment, region, page, span
      ├── locator      the part's address in the source file's own reference system
      ├── parent_part_id   structural containment (scene graphs, frames→regions, utterances→words)
      └── track_id     identity across frames/regions ("this box and that box are the same car")
fields                 the embedded ontology: types, options, taxonomies, constraints, visibility
categories             optional COCO-style primary classes
annotations            values linking parts to fields (with optional provenance)
```

Key rules that keep the format interoperable (all consequences of the core principles above):

- **Geometry rule.** Every drawn instance (2D box, polygon, mask, pose, 3D cuboid) is a `region` part with exactly one geometry-defining annotation. Images, video frames, and meshes all follow the same rule.
- **Constraint enforcement contract.** Constraints are validated at ontology import, honored by the rendered widget, and re-validated at submission. An ontology that imports successfully is guaranteed renderable and answerable.
- **Ontology documents.** A JAMESON file may carry *only* an ontology — making JAMESON a schema-interchange format: author a labeling form anywhere, upload it into a labeling tool, and it renders.

## Supported modalities

| Modality | Modeled as |
| --- | --- |
| Images | `region` parts (bbox, rotated bbox, polygon, polyline, point, keypoints, mask) |
| Multi-mesh 3D assets (GLB/glTF) | `mesh` parts addressed by scene-graph `node_path`, 3D cuboid regions |
| Spreadsheets / tables | `row` parts (sheet + row index) |
| Video | canonical `frame` parts, `region` parts per object appearance, `track` parts for identity |
| Audio | `segment` parts (nested utterance → word), `track` parts for speaker diarization |
| Text / transcripts | `span` parts (code-point character ranges), `track` parts for entity coreference |
| Documents / PDFs | `page` parts, regions on pages |
| Point clouds | 3D geometry types (`bbox3d`, 3D `point`) |
| Whole-file QA / classification | a single `file` part |

## Versions

| Version | Status | Spec | Examples |
| --- | --- | --- | --- |
| [v0.4](v0.4/README.md) | Current draft | [v0.4/README.md](v0.4/README.md) | [v0.4/examples/](v0.4/examples/) |
| [v0.3](v0.3/README.md) | Superseded | [v0.3/README.md](v0.3/README.md) | [v0.3/examples/](v0.3/examples/) |

Each version directory is immutable once superseded: it contains that version's full specification and example documents that conform to it. Minor versions add optional fields and registry entries without breaking existing files; consumers must ignore unknown fields.

## Quick example

A spreadsheet row classified by a form with a radio field:

```json
{
  "jameson_version": "0.4",
  "info": { "description": "Invoice row classification" },
  "files": [ { "id": 1, "file_name": "invoices_q3.xlsx", "file_type": "xlsx" } ],
  "parts": [
    { "id": 501, "file_id": 1, "type": "row",
      "locator": { "sheet": "Sheet1", "row_index": 42 } }
  ],
  "fields": [
    { "id": 1, "name": "risk_level", "label": "Risk Level", "type": "single_select",
      "required": true, "render": "radio",
      "options": [
        { "value": "low", "label": "Low" },
        { "value": "high", "label": "High" }
      ] }
  ],
  "categories": [],
  "annotations": [
    { "id": 5001, "part_id": 501,
      "values": [ { "field_id": 1, "value": "high" } ] }
  ]
}
```

See [v0.4/examples/](v0.4/examples/) for complete documents covering object detection, pose, video multi-object tracking, speech diarization, text NER with coreference, GLB quality review, spreadsheet labeling, PDF labeling, and a standalone ontology document.

## License

This specification is released under the [Creative Commons Attribution 4.0 International License (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/).
