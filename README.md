# krita-plugin-comfyui

Krita plugin that seamlessly integrates with ComfyUI for AI image generation.

Demo videos:

[Realism](https://github.com/Pauan/krita-plugin-comfyui/raw/refs/heads/master/examples/Demo%20realism.mp4)

[Art](https://github.com/Pauan/krita-plugin-comfyui/raw/refs/heads/master/examples/Demo%20art.mp4)

[img2video](https://github.com/Pauan/krita-plugin-comfyui/raw/refs/heads/master/examples/Demo%20video.mp4)


# How to install as a developer

1. Install [uv](https://github.com/astral-sh/uv). You might be able to install it from your distro's package manager.

2. Git clone this repo.

   ```sh
   git clone https://github.com/Pauan/krita-plugin-comfyui.git
   ```

3. Build the project.

   ```sh
   cd krita-plugin-comfyui
   uv run build
   ```

4. Go into your Krita plugin folder, this is usually `~/.local/share/krita/pykrita` on Linux.

   ```sh
   cd ~/.local/share/krita/pykrita
   ```

5. Create symlinks:

   ```sh
   ln -s "/path/to/krita-plugin-comfyui/dist/krita/zip/krita_comfyui" krita_comfyui
   ln -s "/path/to/krita-plugin-comfyui/dist/krita/zip/krita_comfyui.desktop" krita_comfyui.desktop
   ```

6. Go into your ComfyUI custom nodes folder.

   ```sh
   cd "/path/to/comfyui/custom_nodes"
   ```

7. Create a symlink:

   ```sh
   ln -s "/path/to/krita-plugin-comfyui/dist/comfyui/krita_comfyui" krita_comfyui
   ```

8. You can now open up ComfyUI and Krita, everything should be working fine.

9. When you make modifications to the code, you must run `uv run build` again, and you must restart ComfyUI / Krita to see the changes.

10. You can run the type checker with `uv run pyright`
