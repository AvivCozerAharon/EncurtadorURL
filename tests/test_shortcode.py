from shortcode import generate_short_code


def test_generate_short_code_default_length():
    code = generate_short_code()
    assert len(code) == 6


def test_generate_short_code_custom_length():
    code = generate_short_code(length=10)
    assert len(code) == 10


def test_generate_short_code_alphanumeric():
    code = generate_short_code()
    assert code.isalnum()


def test_generate_short_code_is_random():
    codes = {generate_short_code() for _ in range(200)}
    assert len(codes) == 200
