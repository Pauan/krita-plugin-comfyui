from uuid import uuid4
from ...util.krita import Document, Image, Layer


DEFAULT_CANVAS_RESIZE = "do nothing"
DEFAULT_RESIZE_OTHER_LAYERS = False
DEFAULT_RESIZE_ALGORITHM = "Bicubic"

UUIDS_KEY = "krita_comfyui/image_uuids"
IMAGE_METADATA_KEY = "krita_comfyui/image_metadata/"
IMAGE_BYTES_KEY = "krita_comfyui/image_bytes/"

# We use a hardcoded UUID to store the live mode image.
# This lets us reuse all the existing methods, instead
# of creating live mode specific methods.
LIVE_MODE_UUID = "b9618008-c80c-485e-82c9-be9df679be44"


# Deletes elements from the list which the function returns True
def delete_all(list, f):
    indexes = []

    for index in reversed(range(len(list))):
        if f(list[index]):
            indexes.append(index)

    for index in indexes:
        del list[index]


# Class for images which are stored in the document.
class SerializedImage:
    def __init__(self, uuid, image, metadata):
        self.uuid = uuid
        self.image = image
        self.metadata = metadata


    @staticmethod
    def new_uuid():
        uuid = str(uuid4())
        assert uuid != LIVE_MODE_UUID
        return uuid


    @staticmethod
    def live_mode_uuid():
        return LIVE_MODE_UUID


    # Migrates from old image metadata to the new metadata format.
    @staticmethod
    def migrate_metadata(metadata):
        metadata["canvas_resize"] = metadata.get("canvas_resize", DEFAULT_CANVAS_RESIZE)
        metadata["resize_other_layers"] = metadata.get("resize_other_layers", DEFAULT_RESIZE_OTHER_LAYERS)
        metadata["resize_algorithm"] = metadata.get("resize_algorithm", DEFAULT_RESIZE_ALGORITHM)
        return metadata


    @classmethod
    def load_metadata(cls, document, uuid):
        metadata = document.get_key_json(f"{IMAGE_METADATA_KEY}{uuid}", None)

        if metadata is not None:
            metadata = cls.migrate_metadata(metadata)

        return metadata


    @staticmethod
    def load_bytes(document, uuid):
        return document.get_key_bytes(f"{IMAGE_BYTES_KEY}{uuid}", None)


    @classmethod
    def load(cls, document, uuid):
        metadata = cls.load_metadata(document, uuid)

        if metadata is not None:
            bytes = cls.load_bytes(document, uuid)

            if bytes is not None:
                image = Image.from_packed_bytes(bytes, metadata["width"], metadata["height"], swap_rgb=False)
                return SerializedImage(uuid, image, metadata)


    @staticmethod
    def save_new_image(document, uuid, info):
        image = Image.from_base64(info["bytes"], info["width"], info["height"])

        metadata = {
            "format": "rgba",
            "width": info["width"],
            "height": info["height"],
            "x": info["x"],
            "y": info["y"],
            "name": info["name"],
            "canvas_resize": info["canvas_resize"],
            "resize_other_layers": info["resize_other_layers"],
            "resize_algorithm": info["resize_algorithm"],
        }

        serialized = SerializedImage(uuid, image, metadata)

        try:
            serialized.save_bytes(document)
            serialized.save_metadata(document)
        # If something goes wrong, make absolutely sure that we clean up
        except:
            serialized.remove(document)
            raise

        return serialized


    @classmethod
    def save_live_mode(cls, document, info):
        return cls.save_new_image(document, LIVE_MODE_UUID, info)


    def save_bytes(self, document):
        bytes = self.image.bytes()
        document.set_key_bytes(f"{IMAGE_BYTES_KEY}{self.uuid}", "krita_comfyui: Image Bytes", bytes)


    def save_metadata(self, document):
        document.set_key_json(f"{IMAGE_METADATA_KEY}{self.uuid}", "krita_comfyui: Image Metadata", self.metadata)


    def set_metadata_boolean(self, document, key: str, value: bool, *, save=True):
        old_value = self.metadata.get(key, False)

        if old_value != value:
            if value:
                self.metadata[key] = value

            else:
                try:
                    del self.metadata[key]
                except KeyError:
                    pass

            if save:
                self.save_metadata(document)

            return True

        return False


    def is_applied(self):
        return self.metadata.get("applied", False)

    def set_applied(self, document, value, *, save=True):
        return self.set_metadata_boolean(document, "applied", value, save=save)


    def is_selected(self):
        return self.metadata.get("selected", False)

    def set_selected(self, document, value, *, save=True):
        return self.set_metadata_boolean(document, "selected", value, save=save)


    def update_position(self, document, x, y):
        assert x != 0 or y != 0

        self.metadata["x"] -= x
        self.metadata["y"] -= y
        self.save_metadata(document)


    def remove(self, document):
        try:
            document.remove_key(f"{IMAGE_BYTES_KEY}{self.uuid}")
        finally:
            document.remove_key(f"{IMAGE_METADATA_KEY}{self.uuid}")


    def show_preview(self, document):
        name = self.metadata["name"]

        document.show_preview_layer(
            name=f"[Preview] {name}",
            image=self.image,
            x=self.metadata["x"],
            y=self.metadata["y"],
            canvas_resize=self.metadata["canvas_resize"],
        )


# Class for a list of image UUIDs which are stored in the document.
class SerializedImages:
    def __init__(self, uuids):
        self.uuids = uuids
        self.images = {}


    # Migrates from the old format where groups weren't saved.
    @staticmethod
    def migrate_uuids(uuids):
        output = []

        for group in uuids:
            # It's an old style batch, so we wrap it into a group.
            if len(group) > 0 and isinstance(group[0], str):
                output.append([group])
            else:
                output.append(group)

        return output


    @classmethod
    def load(cls, document, *, load_images=True):
        output = SerializedImages(cls.migrate_uuids(document.get_key_json(UUIDS_KEY, [])))
        output.verify_storage_integrity(document)

        if load_images:
            for uuid in output.all_uuids():
                assert uuid != LIVE_MODE_UUID
                assert not uuid in output.images

                output.images[uuid] = SerializedImage.load(document, uuid)

        return output


    # Verifies that there aren't any dangling leftover images in the document.
    def verify_storage_integrity(self, document):
        seen_uuid = set()

        for uuid in self.all_uuids():
            seen_uuid.add(uuid)

        seen_metadata = set()
        seen_bytes = set()

        for key in document.all_keys():
            uuid = key.removeprefix(IMAGE_METADATA_KEY)
            if uuid != key and uuid != LIVE_MODE_UUID:
                assert uuid in seen_uuid
                seen_metadata.add(uuid)

            uuid = key.removeprefix(IMAGE_BYTES_KEY)
            if uuid != key and uuid != LIVE_MODE_UUID:
                assert uuid in seen_uuid
                seen_bytes.add(uuid)

        for uuid in seen_uuid:
            assert uuid in seen_metadata
            assert uuid in seen_bytes


    def all_uuids(self):
        for group in self.uuids:
            for batch in group:
                yield from batch


    def get_image(self, uuid):
        return self.images[uuid]


    def get_images(self):
        return [[[self.images[uuid] for uuid in batch] for batch in group] for group in self.uuids]


    def add_new_group(self, document, group):
        assert len(group) > 0

        new_group = []

        for batch in group:
            assert len(batch) > 0

            new_batch = []

            for info in batch:
                uuid = SerializedImage.new_uuid()
                serialized = SerializedImage.save_new_image(document, uuid, info)
                self.images[uuid] = serialized
                new_batch.append(uuid)

            new_group.append(new_batch)

        self.uuids.append(new_group)
        self.save(document)

        return [[self.images[uuid] for uuid in batch] for batch in new_group]


    def clear(self, document):
        for uuid in self.all_uuids():
            image = self.images.pop(uuid)
            image.remove(document)

        assert self.images == {}
        self.uuids = []
        self.save(document)


    def remove_uuids(self, document, uuids):
        assert len(uuids) > 0

        images = []

        for uuid in uuids:
            image = self.images.pop(uuid)
            image.remove(document)
            images.append(image)

        def remove_batch(batch):
            delete_all(batch, lambda uuid: uuid in uuids)
            return len(batch) == 0

        def remove_group(group):
            delete_all(group, remove_batch)
            return len(group) == 0

        delete_all(self.uuids, remove_group)

        self.save(document)

        return images


    def save(self, document):
        if len(self.uuids) == 0:
            document.remove_key(UUIDS_KEY)
        else:
            document.set_key_json(UUIDS_KEY, "krita_comfyui: Image UUIDs", self.uuids)

        self.verify_storage_integrity(document)


    @staticmethod
    def get_image_bounds(document, images):
        bounds = None
        resize_layers = None
        resize_algorithm = None

        for serialized in images:
            image = serialized.image
            info = serialized.metadata
            image_bounds = None

            match info["canvas_resize"]:
                case "do nothing":
                    pass

                case "increase":
                    image_bounds = Bounds(info["x"], info["y"], image.width, image.height).union(document.bounds())

                case "crop":
                    image_bounds = Bounds(info["x"], info["y"], image.width, image.height)

                case value:
                    raise ValueError(f"canvas_resize has unknown value {value}")

            if image_bounds is not None:
                if bounds is None:
                    bounds = image_bounds
                else:
                    bounds = bounds.union(image_bounds)

                if info["resize_other_layers"]:
                    if resize_algorithm is None:
                        resize_algorithm = info["resize_algorithm"]

                    if resize_layers is None:
                        resize_layers = image_bounds
                    else:
                        resize_layers = resize_layers.union(image_bounds)

        return bounds, resize_layers, resize_algorithm


    @classmethod
    def resize_image_bounds(cls, document, images):
        bounds, resize_layers, resize_algorithm = cls.get_image_bounds(document, images)

        if bounds is not None:
            if resize_layers is not None:
                document.scale_to_bounds(bounds, resize_layers, resize_algorithm)
            else:
                document.resize_to_bounds(bounds)
        else:
            bounds = document.bounds()

        return bounds


    @classmethod
    def apply_new_layers(cls, document, images):
        # This ensures that the canvas bounds will be properly reset to normal.
        document.remove_preview_layer()

        bounds = cls.resize_image_bounds(document, images)

        for serialized in images:
            layer = Layer.fromImage(
                document,
                serialized.metadata["name"],
                serialized.image,
                serialized.metadata["x"] - bounds.x,
                serialized.metadata["y"] - bounds.y,
            )
            layer.move_to_top(document.root_layer())

            #activeLayer = document.active_layer()
            #parent = activeLayer.parent
            #parent.insert_child(layer, activeLayer)

        return bounds


    @classmethod
    def apply_existing_layer(cls, document, images):
        # This ensures that the canvas bounds will be properly reset to normal.
        document.remove_preview_layer()

        bounds = cls.resize_image_bounds(document, images)

        active_layer = document.active_layer()
        parent = active_layer.parent

        for serialized in images:
            # The write_image method does not blend with the existing layer, it completely overwrites the pixels.
            # So in order to blend properly, we create a new layer and then merge it with the active layer.
            layer = Layer.fromImage(
                document,
                serialized.metadata["name"],
                serialized.image,
                serialized.metadata["x"] - bounds.x,
                serialized.metadata["y"] - bounds.y,
            )
            parent.insert_child(layer, active_layer)
            layer.merge_down()

        return bounds


    @classmethod
    def apply_new_document(cls, document, images):
        # This ensures that the canvas bounds will be properly reset to normal.
        #
        # If we use remove_preview_layer then it causes the global selection mask to break.
        document.hide_preview_layer()

        bounds, resize_layers, resize_algorithm = cls.get_image_bounds(document, images)

        if bounds is None:
            bounds = document.bounds()

        profile = document.color_profile()
        resolution = document.pixels_per_inch()

        new_document = Document.create(
            bounds.width,
            bounds.height,
            document.name,
            # TODO copy these from the existing document?
            "RGBA",
            "U8",
            profile,
            resolution,
        )

        for layer in new_document.root_layer().all_children():
            layer.remove()

        for serialized in images:
            layer = Layer.fromImage(
                new_document,
                serialized.metadata["name"],
                serialized.image,
                serialized.metadata["x"] - bounds.x,
                serialized.metadata["y"] - bounds.y,
            )
            new_document.root_layer().insert_child(layer, None)
