from calculator import add, subtract, multiply, divide, power, factorial


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(5, 3) == 2


def test_multiply():
    assert multiply(4, 3) == 12


def test_divide():
    assert divide(10, 2) == 5.0


def test_power():
    assert power(2, 3) == 8
    assert power(0, 0) == 1


def test_factorial():
    assert factorial(5) == 120
    assert factorial(0) == 1
