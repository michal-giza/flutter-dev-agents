from mcp_phone_controll.domain.failures import Failure, UnexpectedFailure
from mcp_phone_controll.domain.result import Err, Ok, err, ok


def test_ok_flags():
    r = ok(42)
    assert r.is_ok and not r.is_err
    assert isinstance(r, Ok)
    assert r.value == 42


def test_err_flags():
    f = UnexpectedFailure(message="boom")
    r = err(f)
    assert r.is_err and not r.is_ok
    assert isinstance(r, Err)
    assert r.failure is f
    assert r.failure.code == "UnexpectedFailure"


def test_failure_code_is_class_name():
    assert Failure(message="x").code == "Failure"
    assert UnexpectedFailure(message="x").code == "UnexpectedFailure"
