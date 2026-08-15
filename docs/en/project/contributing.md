# Contributing

[日本語版](../../ja/project/contributing.md)

1. Keep all source-code comments and docstrings in English.
2. Keep KiCad wrapper logic inside `plugin/emi_guardian/kicad_adapter.py`; analysis modules must operate on immutable domain models.
3. Add a regression test for every compatibility workaround or board-mutation safety rule.
4. Do not lower a safety gate to make a test board pass. Add an explicit, documented parameter instead.
5. Run the complete verification sequence from the root README before submitting changes.
6. Document algorithm changes in both `docs/en` and `docs/ja`.

Automatic board writes must remain opt-in, transactional, same-net verified, and reversible. New quantitative calculations must expose assumptions and a validity disclaimer.
