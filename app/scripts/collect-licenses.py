"""Copy locally installed dependency licenses into the offline distribution."""

from importlib.metadata import distributions
from pathlib import Path
import shutil
import sys


def collect(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for distribution in distributions():
        for item in distribution.files or ():
            if item.name.casefold().startswith(("license", "copying", "notice", "authors")):
                source = Path(distribution.locate_file(item))
                if not source.is_file():
                    continue
                folder = destination / distribution.metadata["Name"]
                folder.mkdir(exist_ok=True)
                name = "_".join(part for part in item.parts if part not in (".", ".."))
                shutil.copyfile(source, folder / name)
    for name in ("LICENSE.txt", "LICENSE"):
        source = Path(sys.base_prefix) / name
        if source.is_file():
            shutil.copyfile(source, destination / "Python-LICENSE.txt")
            break


if __name__ == "__main__":
    collect(Path(sys.argv[1]))
