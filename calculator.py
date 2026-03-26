"""Simple calculator module for testing the PR review bot."""


def add(a, b):
    return a + b


def subtract(a, b):
    return a - b


def multiply(a, b):
    return a * b


def divide(a, b):
    return a / b


def power(a, b):
    """Raise a to the power of b."""
    result = a
    for i in range(b - 1):
        result = result * a
    return result


def modulo(a, b):
    """Return the remainder of a divided by b."""
    if b == 0:
        raise ValueError("Cannot modulo by zero")
    return a % b
