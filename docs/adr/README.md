# Architecture Decision Records

Decisions worth remembering live here. One file per decision, named
`NNNN-short-slug.md`, immutable once `Status: accepted`. Use ADR-0000
as the template.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-image-cap.md) | Cap returned PNG paths at 1920px long-edge | accepted |
| [0002](0002-middleware-chain.md) | Dispatcher as a middleware chain | accepted |
| [0003](0003-version-handshake.md) | `mcp_ping` + boot self-check log | accepted |
| [0004](0004-voyager-skill-library.md) | Voyager-style skill library | accepted |
| [0005](0005-hybrid-retrieval.md) | Hybrid dense + lexical retrieval | accepted |

## When to write one

- A choice affects how multiple modules talk to each other.
- We rejected an obvious alternative and the reason isn't visible in
  the code.
- A future maintainer would reasonably re-litigate the decision.

If it fits in a commit message, it's a commit message. If it's worth
remembering six months later, it's an ADR.
