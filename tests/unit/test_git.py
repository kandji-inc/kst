import contextlib
import logging
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from kst import git
from kst.exceptions import InvalidRepositoryError


@pytest.fixture
def tmp_path_git_cd(git_repo):
    """Change the working directory to a temporary git repository and return the path."""
    with contextlib.chdir(git_repo):
        yield git_repo


class TestGitCommand:
    """Tests for the git command wrapper."""

    @pytest.mark.usefixtures("tmp_path_git_cd")
    def test_git_status_cwd(self):
        """Ensure the git function returns a subprocess.CompletedProcess as a result if successful."""
        result = git.git("status")
        assert isinstance(result, subprocess.CompletedProcess)
        assert result.returncode == 0
        assert "On branch main" in result.stdout

    def test_git_status_cd_path(self, git_repo):
        """Ensure the git function changes the working directory when the cd_path argument is provided."""
        result = git.git("status", cd_path=git_repo)
        assert isinstance(result, subprocess.CompletedProcess)
        assert result.returncode == 0
        assert "On branch main" in result.stdout

    def test_git_init(self, tmp_path):
        assert not (tmp_path / ".git").exists()
        result = git.git("init", cd_path=tmp_path)
        assert isinstance(result, subprocess.CompletedProcess)
        assert result.returncode == 0
        assert (tmp_path / ".git").exists()
        assert "Initialized empty Git repository" in result.stdout

    @pytest.mark.usefixtures("git_remote")
    def test_add_reset_commit_push_workflow(self, git_repo):
        """Ensure the git function can add files to the index."""

        with contextlib.chdir(git_repo):
            # create a file and add it to the index
            (git_repo / "file01.txt").write_text("test")
            git.git("add", "file01.txt")
            result = git.git("status")
            assert "Changes to be committed" in result.stdout
            assert re.search(r"new file:\s+file01.txt", result.stdout) is not None

            # create a second file and add all files to the index
            (git_repo / "file02.txt").write_text("test")
            git.git("add", "--all")
            result = git.git("status")
            assert "Changes to be committed" in result.stdout
            assert re.search(r"new file:\s+file01.txt", result.stdout) is not None
            assert re.search(r"new file:\s+file02.txt", result.stdout) is not None

            # reset the first file
            git.git("reset", "file01.txt")
            result = git.git("status")
            assert "Changes to be committed" in result.stdout
            assert re.search(r"new file:\s+file02.txt", result.stdout) is not None
            assert "Untracked files" in result.stdout
            assert "file01.txt" in result.stdout

            # commit the second file
            result = git.git("commit", "-m", "added file02.txt")
            assert "1 file changed" in result.stdout
            assert "create mode 100644 file02.txt" in result.stdout

            # push the commit to the remote
            result = git.git("push")
            assert "main -> main" in result.stderr

    def test_expected_exit_code(self, tmp_path):
        """Ensure the setting the correct expected exit code suppresses exceptions."""
        assert not (tmp_path / ".git").exists()
        git.git("status", cd_path=tmp_path, expected_exit_code=128)

    def test_git_error(self, tmp_path):
        """Ensure the git function raises an exception when the git command fails."""
        assert not (tmp_path / ".git").exists()
        with pytest.raises(git.GitRepositoryError):
            git.git("status", cd_path=tmp_path, expected_exit_code=0)


class TestLocateGit:
    """Tests for the _locate_git function."""

    def test_locate_git(self):
        """Ensure the _locate_git function returns the path to the git executable."""
        assert git.locate_git().endswith("git")

    def test_git_missing(self, monkeypatch):
        """Ensure the _locate_git function raises an exception when the git executable is missing."""

        monkeypatch.setattr("shutil.which", lambda _: None)
        with pytest.raises(FileNotFoundError, match=r"Failed to locate the git executable\."):
            git.locate_git()

    def test_git_execution_error(self, monkeypatch):
        """Ensure the _locate_git function raises an exception when the git executable is not working."""

        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(returncode=1, cmd=" ".join(*args), stderr="error executing git")

        monkeypatch.setattr(subprocess, "run", mock_run)
        with pytest.raises(FileNotFoundError, match=r"Git execution yielded unexpected result: error executing git"):
            git.locate_git()

    def test_locate_git_cached_response(self):
        """Ensure the _locate_get function caches the result and doesn't needlessly generate a subprocess."""
        git_path = git.locate_git()

        for _ in range(10):
            assert git_path == git.locate_git()

        assert git.locate_git.cache_info().misses == 1
        assert git.locate_git.cache_info().hits == 10


class TestLocateRoot:
    """Tests for the locate_root function."""

    def test_repo_check_cache(self, git_repo):
        """Ensure the locate_root function caches the result and doesn't needlessly call subprocess run."""
        for _ in range(10):
            git.locate_root(cd_path=git_repo, check_marker=False)

        assert git.locate_root.cache_info().misses == 1
        assert git.locate_root.cache_info().hits == 9

        subdir = git_repo / "subdir"
        subdir.mkdir()
        git.locate_root(cd_path=subdir, check_marker=False)

        assert git.locate_root.cache_info().misses == 2

        git.locate_root(cd_path=git_repo, check_marker=False)

        assert git.locate_root.cache_info().hits == 10

    def test_locate_repo_invalid_repo(self, tmp_path):
        """Ensure the locate_root function raises an exception when the repository is invalid."""
        with pytest.raises(InvalidRepositoryError):
            git.locate_root(cd_path=tmp_path)

    def test_locate_existing_parent(self, git_repo):
        """Ensure the locate_root function returns the root of the repository."""
        assert git.locate_root(cd_path=git_repo / "some/other/non_existent/path.txt", check_marker=False) == git_repo

    def test_failed_locate_existing_parent_raises(self):
        """Ensure the locate_root function returns the root of the repository."""
        with pytest.raises(InvalidRepositoryError, match=r"Failed to locate an existing parent directory"):
            git.locate_root(cd_path=Path("/non_existent/path.txt"))

    def test_root_marker_in_subdir(self, git_repo):
        """Ensure the locate_root function returns the root of the repository when the marker is in a subdirectory."""
        subdir = git_repo / "subdir"
        subdir.mkdir()
        (subdir / ".kst").touch()
        assert git.locate_root(cd_path=subdir / "another_dir", check_marker=True) == git_repo / "subdir"

    def test_git_root_marker_in_subdir(self, git_repo):
        """Ensure the locate_root function returns the root of the git repository when the check marker is False and the marker is in a subdirectory."""
        subdir = git_repo / "subdir"
        subdir.mkdir()
        (subdir / ".kst").touch()
        assert git.locate_root(cd_path=subdir, check_marker=False) == git_repo

    def test_check_marker(self, git_repo):
        with pytest.raises(InvalidRepositoryError, match="does not appear to be a Kandji Sync Toolkit repository"):
            git.locate_root(cd_path=git_repo, check_marker=True)


class TestCommitAllChanges:
    """Tests for the commit_all_changes function."""

    def test_no_changes(self, kst_repo, caplog):
        """Ensure the commit_all_changes function does nothing when there are no changes."""
        caplog.set_level(logging.DEBUG)
        git.commit_all_changes(cd_path=kst_repo, message="test", include_body=False)
        assert "No changes to commit" in caplog.text

    def test_unstaged_changes(self, kst_repo, caplog):
        """Ensure the commit_all_changes function stages and commits unstaged changes."""
        caplog.set_level(logging.DEBUG)
        (kst_repo / "file01.txt").write_text("test")
        (kst_repo / "file02.txt").write_text("test2")
        git.commit_all_changes(cd_path=kst_repo, message="test commit", include_body=False)
        assert "Changes committed. 2 files changed," in caplog.text
        status = git.git("log", "--oneline", "-1", cd_path=kst_repo)
        assert "test commit" in status.stdout

    def test_staged_changes(self, kst_repo, caplog):
        """Ensure the commit_all_changes function commits staged changes."""
        caplog.set_level(logging.DEBUG)
        (kst_repo / "file01.txt").write_text("test")
        (kst_repo / "file02.txt").write_text("test2")
        git.git("add", "--all", cd_path=kst_repo)
        if git.git("diff", "--staged", "--exit-code", cd_path=kst_repo).returncode != 1:
            pytest.fail("Failed to stage changes for test.")
        git.commit_all_changes(cd_path=kst_repo, message="test commit", include_body=False)
        assert "Changes committed. 2 files changed," in caplog.text
        status = git.git("log", "--oneline", "-1", cd_path=kst_repo)
        assert "test commit" in status.stdout

    def test_commit_with_scope(self, kst_repo: Path):
        profile_path = kst_repo / "profiles/Test Profile"
        profile_path.mkdir(parents=True)
        (profile_path / "info.yaml").write_text("test")
        (profile_path / "profile.mobileconfig").write_text("test")

        script_path = kst_repo / "scripts/Test Script"
        script_path.mkdir(parents=True)
        (script_path / "info.yaml").write_text("test")
        (script_path / "audit.sh").write_text("test")
        (script_path / "remediation.sh").write_text("test")

        result = git.git("status", cd_path=kst_repo)
        assert "profiles/" in result.stdout
        assert "scripts/" in result.stdout
        git.commit_all_changes(cd_path=kst_repo, message="test commit", scope=kst_repo / "profiles")
        result = git.git("status", cd_path=kst_repo)
        assert "profiles/" not in result.stdout
        assert "scripts/" in result.stdout


def test_generate_commit_body(kst_repo: Path):
    """Ensure the generate_commit_body function generates the expected commit body."""

    profile_path = kst_repo / "profiles/Test Profile"
    profile_path.mkdir(parents=True)
    (profile_path / "info.yaml").write_text("test")
    (profile_path / "profile.mobileconfig").write_text("test")

    script_path = kst_repo / "scripts/Test Script"
    script_path.mkdir(parents=True)
    (script_path / "info.yaml").write_text("test")
    (script_path / "audit.sh").write_text("test")
    (script_path / "remediation.sh").write_text("test")

    (kst_repo / "README.md").write_text("# Kandji Sync Toolkit Repository")

    # Check that the commit body reflects the scope
    git.git("add", str(kst_repo / "profiles"), cd_path=kst_repo)
    message_body = git.generate_commit_body(repo=kst_repo, stage=True)
    assert message_body == (
        "--- Profiles Added ---\n* profiles/Test Profile/info.yaml\n* profiles/Test Profile/profile.mobileconfig"
    )

    git.git("add", "--all", cd_path=kst_repo)
    message_body = git.generate_commit_body(repo=kst_repo, stage=True)
    assert message_body == (
        "--- Profiles Added ---\n"
        "* profiles/Test Profile/info.yaml\n"
        "* profiles/Test Profile/profile.mobileconfig\n"
        "\n"
        "--- Scripts Added ---\n"
        "* scripts/Test Script/audit.sh\n"
        "* scripts/Test Script/info.yaml\n"
        "* scripts/Test Script/remediation.sh\n"
        "\n"
        "--- Other Added ---\n"
        "* README.md"
    )
    git.git("commit", "-m", "create files", cd_path=kst_repo)

    (profile_path / "info.yaml").write_text("changed")
    (profile_path / "profile.mobileconfig").write_text("changed")

    (script_path / "info.yaml").write_text("changed")
    (script_path / "audit.sh").write_text("changed")
    (script_path / "remediation.sh").write_text("changed")

    git.git("add", "--all", cd_path=kst_repo)
    message_body = git.generate_commit_body(repo=kst_repo, stage=True)
    assert message_body == (
        "--- Profiles Modified ---\n"
        "* profiles/Test Profile/info.yaml\n"
        "* profiles/Test Profile/profile.mobileconfig\n"
        "\n"
        "--- Scripts Modified ---\n"
        "* scripts/Test Script/audit.sh\n"
        "* scripts/Test Script/info.yaml\n"
        "* scripts/Test Script/remediation.sh"
    )
    git.git("commit", "-m", "modify files", cd_path=kst_repo)

    shutil.rmtree(profile_path)
    shutil.rmtree(script_path)
    git.git("add", "--all", cd_path=kst_repo)
    message_body = git.generate_commit_body(repo=kst_repo, stage=True)
    assert message_body == (
        "--- Profiles Deleted ---\n"
        "* profiles/Test Profile/info.yaml\n"
        "* profiles/Test Profile/profile.mobileconfig\n"
        "\n"
        "--- Scripts Deleted ---\n"
        "* scripts/Test Script/audit.sh\n"
        "* scripts/Test Script/info.yaml\n"
        "* scripts/Test Script/remediation.sh"
    )


def test_git_status_from_status(git_repo):
    """Ensure the git status function returns the correct status."""
    assert git.GitStatus.from_status("A") == git.GitStatus.ADDED
    assert git.GitStatus.from_status("M") == git.GitStatus.MODIFIED
    assert git.GitStatus.from_status("D") == git.GitStatus.DELETED
    assert git.GitStatus.from_status("R") == git.GitStatus.RENAMED
    assert git.GitStatus.from_status("C") == git.GitStatus.COPIED
    assert git.GitStatus.from_status("T") == git.GitStatus.TYPE_CHANGED
    assert git.GitStatus.from_status("U") == git.GitStatus.UNMERGED
    assert git.GitStatus.from_status("X") == git.GitStatus.UNKNOWN


class TestSkipGit:
    """Tests for the skip_git parameter and KST_DISABLE_GIT environment variable."""

    def test_skip_git_parameter_true(self, kst_repo, caplog):
        """Ensure commit_all_changes skips Git operations when skip_git=True."""
        caplog.set_level(logging.DEBUG)
        (kst_repo / "file01.txt").write_text("test")
        
        # Call with skip_git=True
        git.commit_all_changes(cd_path=kst_repo, message="test commit", skip_git=True)
        
        # Verify Git operations were skipped
        assert "Skipping Git operations (disabled via flag or environment variable)" in caplog.text
        
        # Verify no commit was made
        result = git.git("log", "--oneline", cd_path=kst_repo)
        assert "test commit" not in result.stdout

    def test_skip_git_parameter_false(self, kst_repo, caplog):
        """Ensure commit_all_changes performs Git operations when skip_git=False."""
        caplog.set_level(logging.DEBUG)
        (kst_repo / "file01.txt").write_text("test")
        
        # Call with skip_git=False (explicit)
        git.commit_all_changes(cd_path=kst_repo, message="test commit", skip_git=False)
        
        # Verify Git operations were NOT skipped
        assert "Skipping Git operations" not in caplog.text
        
        # Verify commit was made
        result = git.git("log", "--oneline", cd_path=kst_repo)
        assert "test commit" in result.stdout

    def test_env_var_disable_git_1(self, kst_repo, caplog, monkeypatch):
        """Ensure KST_DISABLE_GIT=1 skips Git operations."""
        caplog.set_level(logging.DEBUG)
        monkeypatch.setenv("KST_DISABLE_GIT", "1")
        (kst_repo / "file01.txt").write_text("test")
        
        git.commit_all_changes(cd_path=kst_repo, message="test commit")
        
        assert "Skipping Git operations (disabled via flag or environment variable)" in caplog.text
        result = git.git("log", "--oneline", cd_path=kst_repo)
        assert "test commit" not in result.stdout

    def test_env_var_disable_git_true(self, kst_repo, caplog, monkeypatch):
        """Ensure KST_DISABLE_GIT=true skips Git operations."""
        caplog.set_level(logging.DEBUG)
        monkeypatch.setenv("KST_DISABLE_GIT", "true")
        (kst_repo / "file01.txt").write_text("test")
        
        git.commit_all_changes(cd_path=kst_repo, message="test commit")
        
        assert "Skipping Git operations (disabled via flag or environment variable)" in caplog.text
        result = git.git("log", "--oneline", cd_path=kst_repo)
        assert "test commit" not in result.stdout

    def test_env_var_disable_git_yes(self, kst_repo, caplog, monkeypatch):
        """Ensure KST_DISABLE_GIT=yes skips Git operations."""
        caplog.set_level(logging.DEBUG)
        monkeypatch.setenv("KST_DISABLE_GIT", "yes")
        (kst_repo / "file01.txt").write_text("test")
        
        git.commit_all_changes(cd_path=kst_repo, message="test commit")
        
        assert "Skipping Git operations (disabled via flag or environment variable)" in caplog.text
        result = git.git("log", "--oneline", cd_path=kst_repo)
        assert "test commit" not in result.stdout

    def test_env_var_disable_git_case_insensitive(self, kst_repo, caplog, monkeypatch):
        """Ensure KST_DISABLE_GIT is case-insensitive."""
        caplog.set_level(logging.DEBUG)
        monkeypatch.setenv("KST_DISABLE_GIT", "TRUE")
        (kst_repo / "file01.txt").write_text("test")
        
        git.commit_all_changes(cd_path=kst_repo, message="test commit")
        
        assert "Skipping Git operations (disabled via flag or environment variable)" in caplog.text
        result = git.git("log", "--oneline", cd_path=kst_repo)
        assert "test commit" not in result.stdout

    def test_env_var_disable_git_invalid_value(self, kst_repo, caplog, monkeypatch):
        """Ensure invalid KST_DISABLE_GIT values don't skip Git operations."""
        caplog.set_level(logging.DEBUG)
        monkeypatch.setenv("KST_DISABLE_GIT", "maybe")
        (kst_repo / "file01.txt").write_text("test")
        
        git.commit_all_changes(cd_path=kst_repo, message="test commit")
        
        # Should NOT skip Git operations
        assert "Skipping Git operations" not in caplog.text
        result = git.git("log", "--oneline", cd_path=kst_repo)
        assert "test commit" in result.stdout

    def test_skip_git_parameter_overrides_env_var(self, kst_repo, caplog, monkeypatch):
        """Ensure skip_git parameter takes precedence over environment variable."""
        caplog.set_level(logging.DEBUG)
        monkeypatch.setenv("KST_DISABLE_GIT", "0")  # Env var says don't skip
        (kst_repo / "file01.txt").write_text("test")
        
        # But parameter says skip
        git.commit_all_changes(cd_path=kst_repo, message="test commit", skip_git=True)
        
        assert "Skipping Git operations (disabled via flag or environment variable)" in caplog.text
        result = git.git("log", "--oneline", cd_path=kst_repo)
        assert "test commit" not in result.stdout

    def test_no_changes_with_skip_git(self, kst_repo, caplog):
        """Ensure skip_git works even when there are no changes."""
        caplog.set_level(logging.DEBUG)
        
        # No files created, so no changes
        git.commit_all_changes(cd_path=kst_repo, message="test commit", skip_git=True)
        
        assert "Skipping Git operations (disabled via flag or environment variable)" in caplog.text
