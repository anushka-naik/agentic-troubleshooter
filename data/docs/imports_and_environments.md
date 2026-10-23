# Imports, Packages and Environments

Source: https://docs.python.org/3/tutorial/venv.html
Source: https://packaging.python.org/en/latest/tutorials/installing-packages/

## ModuleNotFoundError

```
ModuleNotFoundError: No module named 'pandas'
```

`ModuleNotFoundError` is a subclass of `ImportError` raised when the import system cannot locate a module on `sys.path`. When a package was "definitely installed", the cause is almost always that it was installed into a different interpreter than the one running the code.

## Interpreter mismatch

Each Python interpreter and each virtual environment has its own `site-packages` directory. `pip` installs into the interpreter it belongs to, which is not necessarily the one that runs your script. Typical situations:

- A virtual environment exists but is not activated in the current shell.
- The editor or IDE is configured with a different interpreter than the terminal.
- `pip` on `PATH` belongs to a different Python version than `python`.
- A Jupyter kernel points to a different environment than the one where the package was installed.

## Diagnosing

Run these from the same place the failing code runs:

```bash
python -c "import sys; print(sys.executable)"
python -m pip --version
python -m pip show pandas
```

`sys.executable` shows which interpreter is running; `python -m pip --version` shows which environment pip targets.

## Fixes

Install with the module form of pip, which guarantees the same interpreter:

```bash
python -m pip install pandas
```

Create and activate a virtual environment per project:

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

Then select `.venv` as the interpreter in the editor.

## Distribution name versus import name

Some packages are installed under one name and imported under another, for example `pip install scikit-learn` / `import sklearn`, `pip install Pillow` / `import PIL`, `pip install PyYAML` / `import yaml`, `pip install beautifulsoup4` / `import bs4`.

## Shadowing a module

A local file with the same name as a library shadows it. A file named `random.py`, `json.py` or `requests.py` next to your script is imported instead of the real module, leading to errors such as `AttributeError: module 'requests' has no attribute 'get'`. Rename the local file and delete any stale `__pycache__` directory.

## Circular imports

`ImportError: cannot import name 'X' from partially initialized module 'Y' (most likely due to a circular import)` means two modules import each other at module load time. Move the shared code into a third module, or import inside the function that needs it.
