# Contributing

Keep changes focused, in English, and compatible with Python 3.10 or newer. Do not add runtime dependencies without a clear portability benefit.

Before opening a pull request, run:

```bash
python3 -m unittest discover -s tests -v
python3 -m agent_loop doctor
```

Tests must not call paid model APIs. Use `tests/mock_agent.py` for deterministic coordinator behavior.
