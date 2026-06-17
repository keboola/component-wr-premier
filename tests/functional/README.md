# Functional (datadir) tests

Each subdirectory here is one datadir test case with this layout:

```
<test_name>/
  source/data/config.json        # the component config for this case
  source/data/in/tables/*.csv     # input tables
  expected/data/out/tables/*.csv  # expected output (e.g. results.csv)
```

`DataDirTester` runs `src/component.py` against each case's `source/data` and compares the produced `out/` against `expected/`.

- Directories whose name starts with `_` are SKIPPED (use this for templates / not-yet-recorded cases).
- Because this is a **writer**, live cases need VCR cassettes (recorded HTTP) so tests don't hit a real PREMIER server. Cassettes + `secrets.json` + `VCR_SANITIZERS` are added in the VCR test phase (see the build plan). Until then, only the skipped `_example_*` template exists.
