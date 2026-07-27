import pytest

from mini_infer import __version__
from mini_infer.cli import main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as captured:
        main(["--version"])
    assert captured.value.code == 0
    assert capsys.readouterr().out.strip() == f"mini-infer {__version__}"


def test_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as captured:
        main(["--help"])
    assert captured.value.code == 0
    assert "extensible LLM inference pipeline" in capsys.readouterr().out

