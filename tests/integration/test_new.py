from typer.testing import CliRunner

from kst import app

runner = CliRunner(mix_stderr=False)


def test_help():
    result = runner.invoke(app, ["new", "--help"])
    assert result.exit_code == 0
    assert "Usage: kst new" in result.stdout
    assert "Create a new repository" in result.stdout
    assert "A Path to the directory where the new repository" in result.stdout


def test_new(tmp_path):
    repo = tmp_path / "test_repo"
    result = runner.invoke(app, ["new", str(repo)])
    assert result.exit_code == 0
    assert "Created a new kst repository at" in result.stdout
    assert (repo / "README.md").is_file()
    assert (repo / ".gitignore").is_file()
    assert (repo / "profiles").is_dir()
    assert (repo / ".git").is_dir()


def test_new_existing(tmp_path):
    repo = tmp_path / "test_repo"
    repo.mkdir()
    result = runner.invoke(app, ["new", str(repo)])
    assert result.exit_code == 2
    assert "already exists." in result.stderr


def test_new_existing_git(git_repo):
    repo = git_repo / "test_repo"
    result = runner.invoke(app, ["new", str(repo)])
    assert result.exit_code == 2
    assert "is already a git repository" in result.stderr
