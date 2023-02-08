# Patchstorage LV2 Uploader
Proof of concept utility for uploading LV2 plugins to [patchstorage.com](https://patchstorage.com/platform/lv2-plugins/).

# IMPORTANT
- For recommended plugin build workflow, see [patchstorage-lv2-builder](https://github.com/patchstorage/patchstorage-lv2-builder). 
- Tested on Windows only.
- Currently, the LV2 plugins section on Patchstorage is dedicated to `linux-amd64`, `rpi-aarch64` & `patchbox-os-arm32` builds. Let us know if you would like to see support for additional targets.
- Before uploading a plugin, ensure it wasn’t uploaded by anyone else! If the uploaded version is outdated or missing a specific build, please get in touch with the original uploader on Patchstorage.

# Help Wanted
We are looking for any help with community-based efforts regarding uploading and maintaining LV2 plugins on Patchstorage, helping out with plugin build and contribution guides, and community support aspects on [patchstorage.com](https://patchstorage.com/platform/lv2-plugins/). Reach out to us if you want to help or have any suggestions!

# Installation
- Python 3.7+
- `pip install requests click rdflib`

# Usage
Here are the steps to upload plugins:

1. Clone this repository on your computer.
1. Move plugins you want to upload to the `/plugins` directory. All plugins should be in their corresponding folders inside build target folder, e.g. `/patchstorage-lv2-uploader/plugins/rpi-aarch64/mod-bigmuff.lv2/`
1. Run `python ./uploader.py prepare all` - this command will generate `*.tar.gz` and `patchstorage.json` files in the `/dist` directory. Some information may be missing, so you will have to modify `plugins.json` or `licenses.json` files.
1. Check the `/dist` folder for the results, especially the `patchstorage.json` files. Make adjustments if needed.
1. Run `python ./uploader push all --username <patchstorage_username>` command and follow the instructions. After uploading a plugin, please check the resulting entry on Patchstorage.
1. If you made any changes to the `plugins.json` or `licenses.json` files, create a pull request to this repo.

# TODO
- Interactive `patchstorage.json` missing fields prompt during the `prepare` step.
