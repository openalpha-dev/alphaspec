# Conformance cases

Each file is `{ "description", "document", "expect": { "valid", "errors", "warnings" } }`.
`errors` and `warnings` are the exact sets of rule codes (`SCHEMA` for any schema failure).

A runtime that claims AlphaSpec 0.1 support must, for every case, accept or reject the
document as `expect.valid` says and report the same error codes. Matching warnings is
recommended.

Add a case for every new rule; the test suite fails if a rule has none.
