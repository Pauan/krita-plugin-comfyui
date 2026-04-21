import subprocess
import zipfile
import os
import shutil
from pathlib import Path

root = Path(__file__).parent


def bundle_package(wheel, out_dir, name, include):
    wheel = Path("dist", wheel)
    out_dir = Path("dist", out_dir)
    zip_dir = out_dir / "zip"

    os.makedirs(zip_dir)

    with zipfile.ZipFile(wheel, "r") as zip:
        files = [path for path in zip.namelist() if path.startswith(name + "/")]
        print(files)
        zip.extractall(members=files, path=zip_dir)

    # Build dependencies
    subprocess.run(["uv", "pip", "install", "--target", zip_dir / name / "site-packages", wheel], cwd=root, check=True)

    for path in include:
        shutil.copy(path, zip_dir / Path(path).name)

    shutil.make_archive(out_dir / name, "zip", root_dir=zip_dir)


# Build the wheel files
subprocess.run(["uv", "build", "--all-packages", "--clear"], cwd=root, check=True)


bundle_package(
    wheel="krita_comfyui-1.0.0-py3-none-any.whl",
    out_dir="krita",
    name="krita_comfyui",
    include=[
        "krita/src/krita_comfyui.desktop",
    ]
)
