This is a mostly comprehensive list of all the differences with [krita-ai-diffusion](https://github.com/Acly/krita-ai-diffusion).


# UI

## New features

* You can now open an output image in a new document.

* You can now apply an output image to an existing layer.

* Detailing is done automatically when inpainting. No more need for a separate face / hand detailer.

* You can now use every processor filter in [comfyui_controlnet_aux](https://github.com/Fannovel16/comfyui_controlnet_aux).

* Bundles for commonly used prompts.

* Easily downloading and using loras from Civitai.

* Converts Danbooru tags based on the model used (Anima, Illustrious, etc.)

* Normalizes Danbooru weights to prevent popular tags from drowning out unpopular tags (idea is similar to https://imaginarium.rocks/prompt-workshop/)

## Bug fixes

* You can now access the Inputs and Outputs even when the ComfyUI server is dead.

* Clicking on an output image to preview it is much more responsive and robust.

* Progress bar is more accurate.

* Cancelling a job happens instantly and is more robust.

* Previewing images that are larger than the current canvas size works.

## Improvements

* The UI is smaller and cleaner.

* The sliders now use Krita sliders, which are a lot nicer.

* The layer selection widget is a lot nicer.

* Live mode is much faster, more robust, and doesn't cause Krita to freeze.

* The output images are automatically organized into separate batches.

* It now has two separate dockers, one for Inputs and one for Outputs.

   This means you can organize and split them however you want, instead of having a single monolithic docker.

   You can still get the old experience by stacking the Inputs on top of the Outputs.

* Double click no longer applies the output image. Use right click to apply.

* Auto-completion within combo boxes is improved.

* Scrolling with the mouse wheel will no longer accidentally change values.

   You can still change values by holding Shift or Ctrl while using the mouse wheel.

* You can lock the dock to a specific width.

* Minor improvements to error messages.


# Custom workflows

* Every feature is accessible as a node in ComfyUI, which means everything can be used in custom workflows:

   * Mask regions are now accessible in custom workflows.

   * Control nets are now accessible in custom workflows.

   * Layer groups (containing multiple images) are now accessible in custom workflows.

   * New nodes for the Krita selection:

      * `Krita Selection: Border` creates a border around the selection.

      * `Krita Selection: Bounds` gives you the x / y / width / height bounds of the selection. This allows you to do custom cropping based on the selection.

      * `Krita Selection: Feather` feathers the selection.

      * `Krita Selection: Grow` grows the selection.

      * `Krita Selection: Invert` inverts the selection.

      * `Krita Selection: Shrink` shrinks the selection.

      * `Krita Selection: Smooth` smooths the selection.

   * New `Krita Debug` node which makes it easier to debug your workflow.

* UI data is saved much more robustly. No more losing your prompts or custom settings.

* Much more powerful UI system for creating custom workflows.

* It's now possible to send images with full alpha transparency between Krita and ComfyUI.

* Transferring images to / from ComfyUI is 100 times faster.

* The `Krita Output` node has more options for resizing the canvas and other layers.

   This is particularly useful when the image is larger than the Krita canvas size (e.g. when upscaling).

* Sending text to Krita is nicer, and it auto-sorts based on the name.

* It pre-compiles the workflow before sending it to ComfyUI. This allows it to do constant evaluation and dead code elimination.

   That means if you have a node which is only sometimes evaluated (like with `Switch`) then it will only be evaluated if needed.

   This is really useful for enabling / disabling mask regions, controlnets, debug output, etc.


# Code quality

* The code is much smaller, cleaner, easier to maintain, faster, and more robust.

* There are fewer dependencies, and all dependencies are locked down and pre-compiled. No more `pip install` hacks at runtime.

* Is multi-threaded, which prevents the UI from freezing.

* Has a robust ComfyUI client implementation in PyQt. This handles connecting to ComfyUI, automatically reconnecting, sending prompts, cancelling prompts, etc.

* Instead of storing a gigantic JSON blob of data inside of `.kra`, it stores only the minimum data that is needed.

* Written from the ground up for Krita 6 and PyQt 6.
