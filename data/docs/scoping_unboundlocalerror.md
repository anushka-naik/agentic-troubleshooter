# Variable Scope and UnboundLocalError

Source: https://docs.python.org/3/faq/programming.html#why-am-i-getting-an-unboundlocalerror-when-the-variable-has-a-value

## How Python decides a name is local

Python determines the scope of a name at compile time. If a name is assigned anywhere inside a function body (including augmented assignment such as `+=`, a `for` target, an `import`, or a `with ... as` target), it is treated as local to that function for the whole function body, unless it is declared `global` or `nonlocal`.

Name resolution follows the LEGB order: Local, Enclosing function, Global (module), Built-in.

## Symptom

Reading the name before the local assignment happens raises:

```
UnboundLocalError: cannot access local variable 'counter' where it is not associated with a value
```

On Python versions before 3.11 the message is `local variable 'counter' referenced before assignment`. `UnboundLocalError` is a subclass of `NameError`.

Example:

```python
counter = 0

def increment():
    counter += 1     # counter is local because it is assigned here
    return counter
```

`counter += 1` reads `counter` before writing it, but the compiler has already classified `counter` as a local variable, so the module-level value is never consulted.

## Fixes

1. Pass state in and return it out. This is usually the best design because it keeps functions pure and testable:

```python
def increment(counter):
    return counter + 1

counter = increment(counter)
```

2. Declare the name `global` when you really intend to rebind a module-level variable:

```python
def increment():
    global counter
    counter += 1
    return counter
```

3. Use `nonlocal` for a variable of an enclosing function (closures):

```python
def make_counter():
    count = 0
    def increment():
        nonlocal count
        count += 1
        return count
    return increment
```

4. Encapsulate state in an object (a class attribute or instance attribute) when several functions share it.

## Conditional assignment

`UnboundLocalError` also occurs when a local variable is assigned only on some code paths:

```python
def label(score):
    if score > 90:
        grade = "A"
    return grade   # fails when score <= 90
```

Assign a default before the branch, or add an `else` branch.
