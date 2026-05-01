"""Imaging modules — download and customize Raspberry Pi OS images."""

from sbc_config.modules.imaging.catalog import (
    list_release_slugs,
    load_release_index,
    release_definition_path,
    release_index_path,
    releases_dir,
    resolve_release_yaml,
)
from sbc_config.modules.imaging.customize import ImagingError, customize_image
from sbc_config.modules.imaging.fetch import download_xz, verify_xz_sha256
from sbc_config.modules.imaging.flash import dd_argv, dd_shell
from sbc_config.modules.imaging.paths import default_cache_dir, repo_root
from sbc_config.modules.imaging.release_spec import PinnedRelease, load_pinned_release

__all__ = [
    "ImagingError",
    "PinnedRelease",
    "customize_image",
    "dd_argv",
    "dd_shell",
    "default_cache_dir",
    "download_xz",
    "list_release_slugs",
    "load_pinned_release",
    "load_release_index",
    "release_definition_path",
    "release_index_path",
    "releases_dir",
    "repo_root",
    "resolve_release_yaml",
    "verify_xz_sha256",
]
