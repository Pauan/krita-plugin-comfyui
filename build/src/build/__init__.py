import subprocess
import zipfile
import os
import shutil
from pathlib import Path
from .workflows.upscale import Upscale

root = Path(__file__).parent.parent.parent.parent


def find_wheel(package):
    wheel = None

    # Find the wheel file
    for path in os.listdir(root / "dist"):
        if path.startswith(package) and path.endswith(".whl"):
            wheel = Path(root, "dist", path)
            break

    assert wheel is not None
    return wheel


def build_package(*, package, out_dir, include=[]):
    out_dir = Path(root, "dist", out_dir)

    # Build the wheel file
    subprocess.run(["uv", "build", "--package", package, "--quiet"], cwd=root, check=True)

    wheel = find_wheel(package)

    os.makedirs(out_dir)

    with zipfile.ZipFile(wheel, "r") as zip:
        files = [path for path in zip.namelist() if (not ".dist-info" in path)]
        zip.extractall(members=files, path=out_dir)

    for path in include:
        path = Path(root, path)
        shutil.copy(path, out_dir / path.name)


def bundle_dependencies(*, package, out_dir, only_local, exclude_local):
    requirements = Path(root, "dist", "requirements.txt")

    output_requirements(
        package=package,
        output_file=requirements,
        only_local=only_local,
        exclude_local=exclude_local,
    )

    out_dir = Path(root, "dist", out_dir)

    subprocess.run([
        "uv", "pip", "install",
        "--requirements", requirements,
        "--target", out_dir,
        "--quiet",
    ], cwd=root, check=True)

    # Cleans up unnecessary junk
    for path in os.listdir(out_dir):
        if path.endswith(".dist-info"):
            shutil.rmtree(out_dir / path)

    os.remove(out_dir / ".lock")

    try:
        shutil.rmtree(out_dir / "bin")
    except FileNotFoundError:
        pass


def build_zip(*, folder, output):
    shutil.make_archive(
        Path(root, "dist", "zip", output),
        "zip",
        root_dir=Path(root, "dist", folder),
    )


def output_requirements(*, package, output_file, exclude_local, only_local):
    if only_local:
        args = ["--only-group", "local"]
    elif exclude_local:
        args = ["--no-group", "local"]
    else:
        args = ["--group", "local"]

    subprocess.run([
        "uv", "export",
        "--format", "requirements.txt",
        "--package", package,
        "--no-dev",
        "--no-editable",
        "--no-emit-project",
        "--no-hashes",
        "--no-header",
        "--no-annotate",
        "--no-sources",
        *args,
        "--output-file", root / "dist" / output_file,
        "--quiet",
    ], cwd=root, check=True)


def clean():
    try:
        shutil.rmtree(root / "dist")
    except FileNotFoundError:
        pass


def build_krita():
    build_package(
        package="krita_plugin",
        out_dir="krita",
        include=[
            "krita/src/krita_comfyui.desktop",
        ]
    )

    bundle_dependencies(
        package="krita_plugin",
        out_dir="krita/krita_comfyui/site-packages",
        only_local=False,
        exclude_local=False,
    )

    build_zip(
        folder="krita",
        output="krita_plugin",
    )


def build_comfyui():
    build_package(
        package="krita_comfyui",
        out_dir="comfyui",
    )

    output_requirements(
        package="krita_comfyui",
        output_file="comfyui/krita_comfyui/requirements.txt",
        only_local=False,
        exclude_local=True,
    )

    bundle_dependencies(
        package="krita_comfyui",
        out_dir="comfyui/krita_comfyui/site-packages",
        only_local=True,
        exclude_local=False,
    )

    build_zip(
        folder="comfyui",
        output="krita_comfyui",
    )


def main():
    Upscale(root).write()

    clean()
    build_comfyui()
    build_krita()
