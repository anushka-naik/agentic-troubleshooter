# Built-in Exceptions Reference

Source: https://docs.python.org/3/library/exceptions.html

## Reading a traceback

A traceback lists stack frames from the outermost call to the innermost. The last line names the exception type and message; the frame directly above it is where the exception was raised. When debugging, start from the bottom and walk upward until you reach the first frame in your own code. Lines such as "During handling of the above exception, another exception occurred" indicate exception chaining; the original cause is printed first.

## TypeError

Raised when an operation is applied to an object of an inappropriate type. Common messages:

- `'NoneType' object is not subscriptable`: indexing a value that is `None`, often the return value of an in-place method or a function without a `return`.
- `unsupported operand type(s) for +: 'int' and 'str'`: mixing types; convert explicitly with `str()` or `int()`.
- `missing 1 required positional argument`: a call does not match the function signature, or a method was called on the class instead of an instance.
- `'coroutine' object is not subscriptable`: an `async def` function was called without `await`.

## KeyError

Raised when a mapping key is not found. Use `dict.get(key, default)` when absence is expected, `key in mapping` to test membership, or `collections.defaultdict` when missing keys should be created automatically.

## AttributeError

Raised when attribute access fails. `'NoneType' object has no attribute 'x'` means the object is `None`; trace back to where it was assigned. `module 'x' has no attribute 'y'` can indicate a local file shadowing a library module.

## IndexError

Raised when a sequence index is out of range. Check lengths before indexing and prefer iteration over manual index arithmetic. Off-by-one errors in `range(len(seq) + 1)` are a frequent cause.

## ValueError

Raised when an argument has the right type but an inappropriate value, such as `int("abc")`. `json.JSONDecodeError` is a subclass of `ValueError`.

## NameError and UnboundLocalError

`NameError` is raised when a name is not found at all. `UnboundLocalError`, a subclass, is raised when a local variable is referenced before it has been bound in the current function.

## RecursionError

Raised when the maximum recursion depth (by default about 1000 frames, see `sys.getrecursionlimit()`) is exceeded. It is a subclass of `RuntimeError`. The usual cause is a missing or unreachable base case, or a property getter that refers to itself. Fix the base case, or rewrite the algorithm iteratively; raising the recursion limit only postpones the failure and risks crashing the interpreter.

## RuntimeError

A generic error for problems that do not fit other categories. Examples include `dictionary changed size during iteration` and `asyncio.run() cannot be called from a running event loop`.

## FileNotFoundError

A subclass of `OSError` raised when a file or directory is requested but does not exist. Relative paths are resolved against the current working directory, not the location of the script; use `pathlib.Path(__file__).parent / "data.csv"` to build paths relative to the source file.
