from uuid import uuid4
from ...util.krita import Image


DEFAULT_CANVAS_RESIZE = "do nothing"
DEFAULT_RESIZE_OTHER_LAYERS = False
DEFAULT_RESIZE_ALGORITHM = "Bicubic"


# Class for retrieving and storing images in a document.
class ImageSerializer:
    UUIDS_KEY = "krita_comfyui/image_uuids"
    IMAGE_METADATA_KEY = "krita_comfyui/image_metadata/"
    IMAGE_BYTES_KEY = "krita_comfyui/image_bytes/"


    # Verifies that there aren't any dangling leftover images in the document.
    def verify_storage_integrity(self, document, uuids):
        seen_uuid = set()

        for group in uuids:
            for batch in group:
                for uuid in batch:
                    seen_uuid.add(uuid)

        seen_metadata = set()
        seen_bytes = set()

        for key in document.all_keys():
            uuid = key.removeprefix(self.IMAGE_METADATA_KEY)
            if uuid != key:
                assert uuid in seen_uuid
                seen_metadata.add(uuid)

            uuid = key.removeprefix(self.IMAGE_BYTES_KEY)
            if uuid != key:
                assert uuid in seen_uuid
                seen_bytes.add(uuid)

        for uuid in seen_uuid:
            assert uuid in seen_metadata
            assert uuid in seen_bytes


    # Migrates from old image metadata to the new metadata format.
    def migrate_metadata(self, metadata):
        metadata["canvas_resize"] = metadata.get("canvas_resize", DEFAULT_CANVAS_RESIZE)
        metadata["resize_other_layers"] = metadata.get("resize_other_layers", DEFAULT_RESIZE_OTHER_LAYERS)
        metadata["resize_algorithm"] = metadata.get("resize_algorithm", DEFAULT_RESIZE_ALGORITHM)
        return metadata


    def load_image_metadata(self, document, uuid):
        metadata = document.get_key_json(f"{self.IMAGE_METADATA_KEY}{uuid}", None)

        if metadata is not None:
            metadata = self.migrate_metadata(metadata)

        return metadata


    def load_image_bytes(self, document, uuid):
        return document.get_key_bytes(f"{self.IMAGE_BYTES_KEY}{uuid}", None)


    def set_image_bytes(self, document, uuid, bytes):
        document.set_key_bytes(f"{self.IMAGE_BYTES_KEY}{uuid}", "krita_comfyui: Image Bytes", bytes)

    def set_image_metadata(self, document, uuid, metadata):
        document.set_key_json(f"{self.IMAGE_METADATA_KEY}{uuid}", "krita_comfyui: Image Metadata", metadata)


    def process_new_image(self, info):
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

        return (image, metadata)


    def save_new_image(self, document, info):
        uuid = str(uuid4())

        image, metadata = self.process_new_image(info)
        bytes = image.bytes()

        try:
            self.set_image_bytes(document, uuid, bytes)
            self.set_image_metadata(document, uuid, metadata)
        # If something goes wrong, make absolutely sure that we clean up
        except:
            self.remove_image(document, uuid)
            raise

        return uuid, image, metadata


    def save_new_group(self, document, group):
        assert len(group) > 0

        uuids = self.get_uuids(document)

        group = [[self.save_new_image(document, info)[0] for info in batch] for batch in group]

        uuids.append(group)
        self.set_uuids(document, uuids)


    def remove_image(self, document, uuid):
        try:
            document.remove_key(f"{self.IMAGE_BYTES_KEY}{uuid}")
        finally:
            document.remove_key(f"{self.IMAGE_METADATA_KEY}{uuid}")


    # Migrates from the old format where groups weren't saved.
    def migrate_uuids(self, uuids):
        output = []

        for group in uuids:
            # It's an old style batch, so we wrap it into a group.
            if len(group) > 0 and isinstance(group[0], str):
                output.append([group])
            else:
                output.append(group)

        return output


    def get_uuids(self, document):
        uuids = self.migrate_uuids(document.get_key_json(self.UUIDS_KEY, []))
        self.verify_storage_integrity(document, uuids)
        return uuids


    def set_uuids(self, document, uuids):
        if len(uuids) == 0:
            document.remove_key(self.UUIDS_KEY)
        else:
            document.set_key_json(self.UUIDS_KEY, "krita_comfyui: Image UUIDs", uuids)

        self.verify_storage_integrity(document, uuids)


    def clear_uuids(self, document):
        document.remove_key(self.UUIDS_KEY)
        self.verify_storage_integrity(document, [])
