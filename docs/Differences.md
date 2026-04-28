# Code quality

* The code is much smaller, cleaner, easier to maintain, faster, and more robust.

* There are fewer dependencies, and all dependencies are locked down and pre-compiled. No more `pip install` hacks at runtime.

* Has a robust ComfyUI client implementation in PyQt. This handles connecting to ComfyUI, automatically reconnecting, sending prompts, cancelling prompts, etc.

* Fully supports Krita 6 and PyQt 6.


# UI

* The UI is smaller and cleaner.

* It has two separate dockers, one for Inputs and one for Outputs.

   This means you can organize and split them however you want, instead of having a single monolithic docker.

* Progress bar is more accurate.

* Cancelling a job happens instantly and is more robust.

* The Outputs are automatically organized into separate batches.

* You can now open an output in a new document.

* You can now apply an output to an existing layer.

* You can now access the Inputs and Outputs even when the ComfyUI server is dead.

* Double click no longer applies the output, instead use right click.

* Clicking on an output to preview it is much more responsive and robust.


# Custom workflows

* Every feature is accessible as a node in ComfyUI, which means everything can be used in custom workflows:

   * Mask regions are now accessible in custom workflows.

   * The selection bounds are now accessible in custom workflows, which means you can now do custom cropping / padding / feathering.

* UI data is saved much more robustly. No more losing your prompts or custom settings.

* Much more powerful UI system for creating custom workflows.
