from kst.console import OutputConsole


def test_long_str(capsys):
    console = OutputConsole()
    long_string = "a" * 1000
    console.print(long_string)
    captured = capsys.readouterr()
    assert long_string == "".join(captured.out.splitlines())
    assert len(captured.out) > 0
