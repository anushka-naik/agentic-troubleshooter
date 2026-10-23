# Mutable Default Arguments

Source: https://docs.python.org/3/faq/programming.html#why-are-default-values-shared-between-objects
Source: https://docs.python.org/3/reference/compound_stmts.html#function-definitions

## Default values are evaluated once

Default parameter values are evaluated once, when the `def` statement is executed, not each time the function is called. The language reference notes that if a default is a mutable object such as a list or dictionary and the function modifies it, the modification is visible in every later call that relies on the default.

## Symptom

There is no exception. Instead, state leaks between calls:

```python
def add_tag(tag, tags=[]):
    tags.append(tag)
    return tags

add_tag("a")   # ['a']
add_tag("b")   # ['a', 'b']  -- unexpected
```

This is a frequent source of "my list keeps growing" or "results from a previous request appear in the next one" bugs, particularly in long-running processes such as web servers.

## Fix: use None as a sentinel

```python
def add_tag(tag, tags=None):
    if tags is None:
        tags = []
    tags.append(tag)
    return tags
```

When `None` is a meaningful argument value, use a dedicated sentinel object (`_MISSING = object()`).

## Related cases

- Dataclasses reject mutable defaults with `ValueError: mutable default <class 'list'> for field tags is not allowed: use default_factory`. Use `field(default_factory=list)`.
- Class attributes defined as mutable objects are shared by all instances. Initialise per-instance containers in `__init__`.

## Verifying the fix

Because the bug does not raise, running the code is not enough to prove it is fixed. Add an assertion or a test that calls the function twice and checks that the second call does not see the first call's data:

```python
assert add_tag("a") == ["a"]
assert add_tag("b") == ["b"]
```
