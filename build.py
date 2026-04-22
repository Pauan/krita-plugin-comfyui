import subprocess
import zipfile
import os
import shutil
from pathlib import Path

root = Path(__file__).parent


def bundle_package(wheel, out_dir, name, zip_name, include):
    wheel = Path("dist", wheel)
    out_dir = Path("dist", out_dir)

    os.makedirs(out_dir)

    with zipfile.ZipFile(wheel, "r") as zip:
        files = [path for path in zip.namelist() if path.startswith(name + "/")]
        zip.extractall(members=files, path=out_dir)

    # Build dependencies
    subprocess.run(["uv", "pip", "install", "--target", out_dir / name / "site-packages", wheel], cwd=root, check=True)

    for path in include:
        shutil.copy(path, out_dir / Path(path).name)

    shutil.make_archive(Path("dist", zip_name), "zip", root_dir=out_dir)


def build_krita():
    # Build the wheel files
    subprocess.run(["uv", "build", "--all-packages", "--clear"], cwd=root, check=True)

    bundle_package(
        wheel="krita_plugin-1.0.0-py3-none-any.whl",
        out_dir="krita",
        name="krita_comfyui",
        zip_name="zip/krita_plugin",
        include=[
            "krita/src/krita_comfyui.desktop",
        ]
    )


def build_comfyui():
    shutil.copytree(Path("comfyui"), Path("dist", "comfyui", "krita_comfyui"))

    subprocess.run([
        "uv", "export",
        "--format", "requirements.txt",
        "--package", "krita_comfyui",
        "--output-file", "dist/comfyui/krita_comfyui/requirements.txt",
    ], cwd=root, check=True)

    shutil.make_archive(Path("dist", "zip", "krita_comfyui"), "zip", root_dir=Path("dist", "comfyui"))


build_krita()
build_comfyui()
