# Optional browser UI

This is the former local browser UI, retained as a separate experiment rather than part of core `fxs`.

It is not installed by `install.sh`, not required by `fxs`, and may evolve independently. Core fxs deliberately stays shell-like and has no Python or browser dependency.

For current development, run the UI from a repository checkout and treat it as an optional sibling product, not an alternate implementation of the fxs containment boundary.

The retained UI source predates the thin-core refactor; its old provider/state conveniences are intentionally not wired back into core fxs. Keep UI-specific compatibility work here rather than adding it to the runtime wrapper.
