# JAMESON v0.6 Examples

Complete, conformant JAMESON documents covering the major labeling scenarios. Section references (§) point into the [v0.6 specification](../README.md).

| File | Scenario | Spec features demonstrated |
| --- | --- | --- |
| [image-object-detection.json](image-object-detection.json) | Vehicle detection in a photo | `region` parts under a `file` part (§12.1 geometry rule), `bbox` values, categories, per-instance form values, whole-image QA on the `file` part |
| [image-pose-keypoints.json](image-pose-keypoints.json) | Human pose estimation | `keypoints` type: named landmark roster + `skeleton` in the definition, per-point `visibility`, omitted-landmark semantics (§9.4) |
| [video-multi-object-tracking.json](video-multi-object-tracking.json) | Two cars tracked across frames | Canonical `frame` parts, `track_id` identity links, identity values on `track` parts vs. per-frame state on regions (§14.2), the `keyframe` field (§14.3), a `segment` scoped to one track (§14.4) |
| [audio-speech-diarization.json](audio-speech-diarization.json) | Interview transcription | Nested `segment` parts (utterance → word, §14.6), speaker diarization via `track` parts, file-level values |
| [text-ner-coreference.json](text-ner-coreference.json) | Named-entity recognition in a news snippet | `span` parts with code-point character ranges (§7, §14.7), nested sentence → mention spans, entity coreference via `track` parts, identity values on tracks vs. mention values on spans (§14.2) |
| [glb-mesh-quality-review.json](glb-mesh-quality-review.json) | 3D asset QA | `mesh` parts with `node_path` locators mirroring the scene graph (§7), conditional fields via `visible_when` (§10), `bbox3d` region in asset scene space (§9.3) |
| [spreadsheet-row-classification.json](spreadsheet-row-classification.json) | Invoice row labeling | `row` parts (§7) carrying the sheet's own invoice IDs as part `source_id` (§6), `cascading_select` with levels + taxonomy (§8.2), a multi-opinion export: model prelabel and labeler opinions beside a reviewer-signed `resolved: true` answer, plus an unresolved row (§12.2) |
| [image-multi-opinion-consensus.json](image-multi-opinion-consensus.json) | Three labelers, a model, and a reviewer on one image | Raw opinions vs. answers (§12.2): partial reviewer opinion, one complete resolved snapshot per part, every drawing as its own `region` part with a separate resolved region (§12.1), `from_annotation_ids` lineage across parts (§12.3), an answer with no `provenance`, and a stray box that is not part of the answer |
| [pdf-document-labeling.json](pdf-document-labeling.json) | Contract review | `page` parts, a `region` drawn on a page, named string `format` constraint (§8.3.1) |
| [ontology-only-document.json](ontology-only-document.json) | Uploadable labeling form | Ontology document with no annotation data (§13): conditional visibility chains, number constraints (`integer`, `exclusive_min`, `step`), `format`, `multi_select` item bounds, partial-path cascading select, a geometry type declaring a drawing tool |
