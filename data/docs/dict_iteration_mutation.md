# Mutating Collections During Iteration

Source: https://docs.python.org/3/library/stdtypes.html#dictionary-view-objects

## RuntimeError: dictionary changed size during iteration

Dictionary views returned by `dict.keys()`, `dict.values()` and `dict.items()` are dynamic: they reflect changes to the underlying dictionary. The documentation warns that iterating over views while adding or deleting entries in the dictionary may raise a `RuntimeError` or fail to iterate over all entries.

In CPython, adding or removing keys while iterating raises:

```
RuntimeError: dictionary changed size during iteration
```

Sets behave the same way and raise `RuntimeError: Set changed size during iteration`.

Example that fails:

```python
for key, value in config.items():
    if value is None:
        del config[key]
```

Updating the value of an existing key during iteration is allowed because the size of the dictionary does not change.

## Fix 1: iterate over a snapshot

Materialise the keys or items into a list before the loop so that the loop no longer depends on the live view:

```python
for key, value in list(config.items()):
    if value is None:
        del config[key]
```

## Fix 2: build a new dictionary

A dictionary comprehension expresses the intent directly and avoids mutation altogether:

```python
config = {key: value for key, value in config.items() if value is not None}
```

This is usually the clearest option. If other references to the original dictionary must observe the change, mutate in place instead (for example with Fix 1, or by collecting keys to delete and deleting them after the loop).

## Lists modified while iterating

Lists do not raise an error when modified during iteration, which makes the bug silent. Removing items while looping causes elements to be skipped because the iterator's index keeps advancing while the list shifts:

```python
nums = [1, 2, 2, 3]
for n in nums:
    if n == 2:
        nums.remove(n)
# nums == [1, 2, 3]  -- one 2 was skipped
```

Use a comprehension (`nums = [n for n in nums if n != 2]`) or iterate over a copy (`for n in nums[:]`).

## Concurrency note

The same `RuntimeError` can appear when one thread iterates over a dictionary while another thread mutates it. In that case, taking a snapshot under a lock, or using a copy per reader, is the appropriate fix.
