# Testing

## Backend Tests

Run from the repository root:

```bash
pytest
```

With the development dependencies:

```bash
pip install -e ".[dev]"
pytest
```

## Frontend Tests

```bash
cd frontend
npm test
```

## Frontend Build

```bash
cd frontend
npm run build
```

## End-to-End Tests

```bash
cd frontend
npm run test:e2e
```

## Documentation Build

```bash
pip install -r docs/requirements.txt
pip install -e .
sphinx-build -b html docs/source docs/_build/html
```

Open:

```text
docs/_build/html/index.html
```
