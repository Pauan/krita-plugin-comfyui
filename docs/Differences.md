# UI

## New features

* You can now open an output in a new document.

* You can now apply an output to an existing layer.

## Bug fixes

* You can now access the Inputs and Outputs even when the ComfyUI server is dead.

* Clicking on an output to preview it is much more responsive and robust.

* Progress bar is more accurate.

* Cancelling a job happens instantly and is more robust.

## Improvements

* The UI is smaller and cleaner.

* The sliders now use Krita sliders, which are a lot nicer.

* The layer selection widget is a lot nicer.

* The Outputs are automatically organized into separate batches.

* It now has two separate dockers, one for Inputs and one for Outputs.

   This means you can organize and split them however you want, instead of having a single monolithic docker.

   You can still get the old experience by stacking the Inputs on top of the Outputs.

* Double click no longer applies the output, instead use right click.

* Auto-completion within combo boxes is improved.

* Scrolling with the mouse wheel will no longer accidentally change values.

* Minor improvements to error messages.


# Custom workflows

* Every feature is accessible as a node in ComfyUI, which means everything can be used in custom workflows:

   * Mask regions are now accessible in custom workflows.

   * Control nets are now accessible in custom workflows.

   * Layer groups (containing multiple images) are now accessible in custom workflows.

   * The selection bounds are now accessible in custom workflows, which means you can now do custom cropping / padding / feathering.

* UI data is saved much more robustly. No more losing your prompts or custom settings.

* Much more powerful UI system for creating custom workflows.

* It's now possible to send images with full alpha transparency between Krita and ComfyUI.

* Transferring images to / from ComfyUI is 100 times faster.

* Sending text to Krita is nicer, and it auto-sorts based on the name.


# Code quality

* The code is much smaller, cleaner, easier to maintain, faster, and more robust.

* There are fewer dependencies, and all dependencies are locked down and pre-compiled. No more `pip install` hacks at runtime.

* Has a robust ComfyUI client implementation in PyQt. This handles connecting to ComfyUI, automatically reconnecting, sending prompts, cancelling prompts, etc.

* Instead of storing a gigantic JSON blob of data inside of `.kra`, it stores only the minimum data that is needed.

* Fully supports Krita 6 and PyQt 6.
