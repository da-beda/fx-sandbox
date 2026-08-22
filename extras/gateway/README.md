# Optional Gateway Adapter

This directory contains the former OpenAI-compatible protocol adapter. It is intentionally outside core `fxs`.

Core fxs does not know provider catalogs, provider API formats, model defaults, or provider-specific credentials. Use this adapter only when an upstream endpoint still needs translation into the protocol expected by the fx build you are running.

The adapter is not installed by `install.sh` and Python is not present in the reference fxs image. Treat it as an optional compatibility experiment that can be removed once upstream fx covers the required provider path directly.
