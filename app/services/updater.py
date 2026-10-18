"""Download and safely install the latest app files from GitHub."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
import zipfile
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GITHUB_ARCHIVE_URL = "https://api.github.com/repos/Soullessrage/atest/zipball/main"
MAX_ARCHIVE_SIZE = 32 * 1024 * 1024
MAX_EXTRACTED_SIZE = 32 * 1024 * 1024
GITHUB_TOKEN_VARIABLES = ("RETRO_PASTEL_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
UPDATABLE_FILES = {
    PurePosixPath("README.md"),
    PurePosixPath("run.bat"),
    PurePosixPath("Run_Pastel_Quest"),
    PurePosixPath("Run_Pastel_Quest.command"),
    PurePosixPath("app/main.py"),
    PurePosixPath("app/game/plane_game.py"),
    PurePosixPath("app/ui/main_window.py"),
    PurePosixPath("app/ui/settings_window.py"),
    PurePosixPath("app/ui/contact_window.py"),
    PurePosixPath("app/services/updater.py"),
}


class GitHubUpdater:
    """Fetch, validate, stage, and replace app files without touching user data."""

    def __init__(self, install_root: Path, on_status: Callable[[str], None]):
        self.install_root = install_root.resolve()
        self.on_status = on_status

    def update(self) -> None:
        """Download the main branch archive and install its allowlisted files."""
        self.on_status("Contacting GitHub...")
        headers = {
            "User-Agent": "Pastel-Quest-Updater",
            "Accept": "application/vnd.github+json",
        }
        token = self._github_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = Request(GITHUB_ARCHIVE_URL, headers=headers)
        try:
            with urlopen(request, timeout=45) as response:
                archive_data = response.read(MAX_ARCHIVE_SIZE + 1)
        except HTTPError as error:
            if error.code in (401, 403, 404):
                raise RuntimeError(
                    f"GitHub denied the update (HTTP {error.code}). If this repository is private, "
                    "sign in with GitHub CLI or configure a token with read-only repository access."
                ) from error
            raise RuntimeError(f"Could not download the update: HTTP {error.code}") from error
        except (OSError, URLError) as error:
            raise RuntimeError(f"Could not download the update: {error}") from error

        if len(archive_data) > MAX_ARCHIVE_SIZE:
            raise RuntimeError("The GitHub source archive exceeded the 32 MB safety limit.")

        with tempfile.TemporaryDirectory(prefix=".pastel-update-", dir=self.install_root) as temporary:
            temporary_root = Path(temporary)
            archive_path = temporary_root / "github-main.zip"
            staged_root = temporary_root / "staged"
            backup_root = temporary_root / "backups"
            staged_root.mkdir()
            backup_root.mkdir()
            archive_path.write_bytes(archive_data)

            self.on_status("Validating downloaded files...")
            staged_files = self._stage_archive(archive_path, staged_root)
            if not (staged_root / "app/main.py").is_file():
                raise RuntimeError("The downloaded archive did not contain a valid app update.")

            self.on_status("Installing update...")
            self._replace_files(staged_files, staged_root, backup_root)
            self._clear_bytecode_cache()

    @staticmethod
    def _github_token() -> str | None:
        for variable in GITHUB_TOKEN_VARIABLES:
            token = os.environ.get(variable, "").strip()
            if token:
                return token

        github_cli = shutil.which("gh")
        if github_cli is None:
            return None
        try:
            result = subprocess.run(
                [github_cli, "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode == 0:
            return result.stdout.strip() or None
        return None

    @staticmethod
    def _stage_archive(archive_path: Path, staged_root: Path) -> list[Path]:
        staged_files = []
        seen_paths = set()
        extracted_size = 0
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    if "\\" in member.filename:
                        raise RuntimeError("The update archive contains an invalid file path.")
                    archive_parts = PurePosixPath(member.filename).parts
                    if len(archive_parts) < 2:
                        continue
                    relative = PurePosixPath(*archive_parts[1:])
                    if relative.is_absolute() or any(part in (".", "..") for part in relative.parts):
                        raise RuntimeError("The update archive contains an unsafe file path.")
                    if relative not in UPDATABLE_FILES:
                        continue
                    if relative in seen_paths:
                        raise RuntimeError(f"The update archive contains a duplicate file: {relative}")
                    if stat.S_ISLNK(member.external_attr >> 16):
                        raise RuntimeError(f"The update archive contains an unsafe symbolic link: {relative}")

                    extracted_size += member.file_size
                    if extracted_size > MAX_EXTRACTED_SIZE:
                        raise RuntimeError("The extracted update exceeded the 32 MB safety limit.")

                    seen_paths.add(relative)
                    target = staged_root.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("xb") as destination:
                        shutil.copyfileobj(source, destination)
                    file_mode = member.external_attr >> 16
                    if file_mode:
                        target.chmod(file_mode & 0o777)
                    staged_files.append(target)
        except zipfile.BadZipFile as error:
            raise RuntimeError("GitHub returned an invalid ZIP archive.") from error
        return staged_files

    def _replace_files(self, staged_files: list[Path], staged_root: Path, backup_root: Path) -> None:
        replaced: list[tuple[Path, Path | None]] = []
        try:
            for staged_file in staged_files:
                relative = staged_file.relative_to(staged_root)
                target = self.install_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.parent.resolve().is_relative_to(self.install_root):
                    raise OSError(f"Refusing to write outside the app folder: {target}")

                backup = None
                if target.exists() or target.is_symlink():
                    backup = backup_root / relative
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                os.replace(staged_file, target)
                replaced.append((target, backup))
        except OSError as error:
            rollback_errors = []
            for target, backup in reversed(replaced):
                try:
                    if backup is None:
                        target.unlink(missing_ok=True)
                    else:
                        os.replace(backup, target)
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
            rollback_note = f" Rollback issues: {'; '.join(rollback_errors)}" if rollback_errors else ""
            raise RuntimeError(f"Could not install the update; previous files were restored: {error}.{rollback_note}")

    def _clear_bytecode_cache(self) -> None:
        for cache_directory in (self.install_root / "app").rglob("__pycache__"):
            if cache_directory.is_dir():
                shutil.rmtree(cache_directory, ignore_errors=True)