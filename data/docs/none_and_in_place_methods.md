# None Values and In-Place Methods

Source: https://docs.python.org/3/library/stdtypes.html#mutable-sequence-types

## Why in-place methods return None

Many methods on mutable built-in types modify the object in place and return `None` rather than a new object. This is a deliberate design choice: returning `None` signals that the original object was changed and prevents code from accidentally relying on a copy.

Common in-place methods that return `None`:

- `list.sort()`, `list.reverse()`, `list.append()`, `list.extend()`, `list.insert()`, `list.remove()`, `list.clear()`
- `dict.update()`, `dict.clear()`
- `set.add()`, `set.update()`, `set.discard()`
- `random.shuffle(seq)`

The Python documentation for `list.sort()` states that it "modifies the sequence in place for economy of space when sorting a large sequence" and that it does not return the sorted sequence, to remind users that it operates by side effect.

## Symptom: 'NoneType' object is not subscriptable

Assigning the result of an in-place method and then indexing or slicing it produces:

```
TypeError: 'NoneType' object is not subscriptable
```

Example:

```python
ranked = scores.sort(reverse=True)
top = ranked[:3]   # ranked is None
```

Related symptoms caused by the same mistake:

- `AttributeError: 'NoneType' object has no attribute 'append'` after `items = items.append(x)`
- `TypeError: 'NoneType' object is not iterable` when looping over the result of `list.reverse()`
- `TypeError: object of type 'NoneType' has no len()`

## Fixes

Use the built-in `sorted()` function, which returns a new sorted list and leaves the input untouched:

```python
ranked = sorted(scores, reverse=True)
top = ranked[:3]
```

Or call the in-place method on its own line and keep using the original name:

```python
scores.sort(reverse=True)
top = scores[:3]
```

Choose `sorted()` when the caller's list must not be mutated (for example, a list passed into a function as an argument). Choose `list.sort()` when mutation is intended and memory matters.

## Functions that implicitly return None

A function without a `return` statement, or with a bare `return`, returns `None`. A frequent cause of `NoneType` errors is a function that only returns on some branches:

```python
def find_user(users, name):
    for user in users:
        if user["name"] == name:
            return user
    # falls through: returns None
```

Callers should check for `None` explicitly (`if result is None:`) or the function should raise an exception such as `LookupError` when nothing is found.

## Comparing with None

Use `is None` / `is not None` rather than `== None`. `None` is a singleton, and `==` can be overridden by custom `__eq__` methods, which makes identity comparison both faster and more reliable.
