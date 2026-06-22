# Documentation Workflow

The documentation is built with Sphinx, MyST Markdown, and Read the Docs.

## Local Build

```bash
pip install -r docs/requirements.txt
pip install -e .
sphinx-build -b html docs/source docs/_build/html
```

## Add a Page

1. Create a Markdown file under `docs/source/`.
2. Add it to the relevant `toctree` in `docs/source/index.md`.
3. Build locally.
4. Fix warnings.
5. Commit and push.

## Read the Docs Files

Important files:

```text
.readthedocs.yaml
docs/requirements.txt
docs/source/conf.py
docs/source/index.md
```

## Publishing on Read the Docs

After pushing to GitHub:

1. create or log into a Read the Docs account;
2. import the GitHub repository;
3. select the branch to build;
4. let Read the Docs detect `.readthedocs.yaml`;
5. start a build;
6. check build logs if it fails.

The root `.readthedocs.yaml` tells Read the Docs to use `docs/source/conf.py` and install `docs/requirements.txt`.
