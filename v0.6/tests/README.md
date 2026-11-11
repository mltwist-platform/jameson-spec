# JAMESON v0.6 conformance tests

Small documents that pin down what a v0.6 validator must accept and reject. They are tooling, not part of the specification: the [specification](../README.md) is the authority, and these files only exercise it.

- `valid/` — edge cases every conforming validator must accept, beyond the everyday shapes in [`../examples/`](../examples/).
- `invalid/` — each file breaks one rule and must be rejected. A broken rule can cause knock-on errors (an ill-formed constraint also makes an existing value fail), but the listed rule is always among them.
- `manifest.json` — every case with its expected result and, for invalid files, the `rule`: the spec section that rejects it (`§16 rule 9`, `§8.6`, …). Each file's `info.description` says what it tests.

Run them with the reference validator:

```
python3 ../validate.py --self-test
```

The self-test validates `examples/` and every manifest case, and fails if a file in `valid/` or `invalid/` is missing from the manifest. An invalid case passes only when an error cites its `rule`.

Another implementation can use the same manifest: accept every `valid: true` file and reject every `valid: false` file. Matching the `rule` is optional for other validators, since their messages will differ.

To add a case, put a small JSON file in `valid/` or `invalid/` and add an entry to `manifest.json`. An invalid file should change one thing in an otherwise valid document.
