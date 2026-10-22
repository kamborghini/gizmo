# Docs

Two kinds of document live here, and they are read differently.

## The living references

Kept true of the code as it is. Two are generated from the code, and CI fails
when either is stale.

| Document | What it is |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the app is put together, where each kind of logic belongs, and how to add to it |
| [DESIGN.md](DESIGN.md) | The page's design rules: tokens, parts, windows, the panel rules |
| [API.md](API.md) | Every route: its door, its terms, its body's model (generated: `make api-doc`) |
| [ENVIRONMENT.md](ENVIRONMENT.md) | Every setting, its default and what it turns on (generated: `make env-doc`) |
| [worldoptions-api.md](worldoptions-api.md) | Notes on the courier's API |

The move tool and the recipe the backend was split by are beside the tool, in
`tools/moves/README.md`; the browser suite's own notes are in
`tests/browser/README.md`.

## The dated records

What was found or decided at the time, named by date and not brought up to date
afterwards. Read one for why something is the way it is; read the living
references for what is true now.

| Folder | What is in it |
|---|---|
| `architecture/` | The September architecture audit and the October stack currency audit |
| `security/` | The September hardening registers and the application security audit |
| `bugs/` | The September bug registers |
| `design/` | The September design reviews, and the mockup the current look was built from (`design/mix/`) |
| `superpowers/specs/` `superpowers/plans/` | The design, then the plan, behind each change since mid-September, by date |
