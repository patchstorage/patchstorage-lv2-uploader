# Work In Progress!

# Patchstorage LV2 Uploader
Proof of concept utility for uploading LV2 plugins to Patchstorage.com - [https://patchstorage.com/platform/lv2-rpi-arm32/](https://patchstorage.com/platform/lv2-rpi-arm32/)

# IMPORTANT
- Tested on Windows only
- Currently, the LV2 section on Patchstorage is dedicated to 32-bit plugins compiled for Raspberry Pi 3/4! Let us know if you would like to see support for additional targets.
- Before uploading a plugin, ensure it wasn’t uploaded by anyone else! If the uploaded version is outdated, please contact the original uploader on Patchstorage.
- At the moment, there is no support for bundles, only one plugin per single Patchstorage entry is allowed.

# Help Wanted
We are looking for any help with community-based efforts regarding `mod-ui` and `mod-host` projects - compiling, uploading, and maintaining plugins on Patchstorage, helping out with plugin build and contribution guides, and community support aspects on [Patchstorage](https://patchstorage.com/platform/lv2-rpi-arm32/) and [Unofficial MOD Community Discord](https://discord.gg/YyRNPVG6ZS). Reach out to us if you would like to help!

# Installation
- Python 3.7+
- `pip install requests click rdflib`

# Usage
Here are the steps to upload plugins:

1. Clone this repository on your computer.
1. Move plugins you want to upload to the `/plugins` directory. All plugins should be in their corresponding folders, e.g. `/patchstorage-lv2-uploader/plugins/mod-bigmuff.lv2/`
1. Run `python ./uploader.py prepare-all` - this command will generate `*.tar.gz` and `patchstorage.json` files in the `/builds` directory. Some information may be missing, so you will have to modify `licenses.json` or `sources.json` files.
1. Check the `/builds` folder for the results, especially the `patchstorage.json` files. Make adjustments if needed.
1. Run `python ./uploader push-all --username <patchstorage_username>` command and follow the instructions. After uploading a plugin, please check the resulting entry on Patchstorage.
1. If you made any changes to the `licenses.json` or `sources.json` files, make a pull request to this repo.

# TODO
- Interactive patchstorage.json missing fields prompt on `prepare` step
- Validate *.tar.gz file contents before uploading