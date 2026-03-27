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


def factorial(n):
    """Calculate the factorial of n."""
    if n < 0:
        raise ValueError("Factorial not defined for negative numbers")
    result = 1
    i = 2
    while i <= n:
        result *= i
        i += 1
    return result
