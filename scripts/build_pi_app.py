"""Um arquivo transferível; dependências nativas continuam externas ao .pyz."""

import argparse
from pathlib import Path
import shutil
import tempfile
import zipapp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    source = Path(__file__).resolve().parents[1] / "src" / "robosense_lab"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        package = Path(temporary) / "robosense_lab"
        package.mkdir()
        for module in source.glob("*.py"):
            shutil.copyfile(module, package / module.name)
        (Path(temporary) / "__main__.py").write_text(
            "from robosense_lab.live import main\nraise SystemExit(main())\n", encoding="utf-8")
        with args.output.open("xb") as output:
            zipapp.create_archive(temporary, target=output, compressed=True)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
