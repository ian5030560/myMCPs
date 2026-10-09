from __future__ import annotations

from mymcps.core.server import BaseMediaServer


class ImageGenServer(BaseMediaServer):
    name = "image_gen"
    cli_name = "image-gen"
    instructions = "Generate and edit images with cloud image models."
    default_port = 8701

    def register_tools(self) -> None:
        pass  # generate_image / edit_image arrive in the next stage


main = ImageGenServer.main
