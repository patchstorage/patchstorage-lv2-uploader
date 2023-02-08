from typing import Optional, Union, Dict
import os
import shutil
import pathlib
import json
import requests
import click
from bundles import PatchstorageMultiTargetBundle, PluginFieldMissing, BundleBadContents


PS_API_URL = 'https://patchstorage.com/api/beta'
PS_LV2_PLATFORM_ID = 8046
PS_TAGS_DEFAULT = ['lv2-plugin', ]
PATH_ROOT = pathlib.Path(__file__).parent.resolve()
PATH_PLUGINS = PATH_ROOT / 'plugins'
PATH_DIST = PATH_ROOT / 'dist'

# for dev purposes
DEBUG = False

if DEBUG:
    PS_API_URL = 'http://localhost/api/beta'
    PS_LV2_PLATFORM_ID = 5027


class PatchstorageException(Exception):
    """Base exception for Patchstorage class errors"""


class Patchstorage:
    """Patchstorage API client class"""
    # TODO: prepare requests and send using a separate staticmethod w/ exception handling

    PS_API_TOKEN = None
    USER_AGENT = 'lv2-plugin-uploader'

    @staticmethod
    def decode_json_response(resp: requests.Response) -> dict:
        """Decode JSON response from Patchstorage API"""

        resp_data: dict = {}

        try:
            resp_data = resp.json()
        except requests.exceptions.JSONDecodeError as err:
            raise PatchstorageException(
                f'Failed to decode JSON response for {resp.url}') from err

        return resp_data

    @staticmethod
    def auth(username: str, password: str) -> None:
        """Authenticate with Patchstorage API"""

        assert PS_API_URL is not None
        assert username
        assert password

        url = PS_API_URL + '/auth/token'

        click.echo(f'Authenticating: {username} ({url})')

        resp = requests.post(url, data={
            'username': username,
            'password': password
        }, headers={'User-Agent': Patchstorage.USER_AGENT})

        resp_data = Patchstorage.decode_json_response(resp)

        if not resp.ok:
            raise PatchstorageException('Failed to authenticate')

        Patchstorage.PS_API_TOKEN = resp_data['token']

    @staticmethod
    def get_platform_targets(platform_id: int) -> list:
        """Get supported targets for a given platform ID"""

        assert PS_API_URL is not None

        url = f"{PS_API_URL}/platforms/{platform_id}"

        click.echo(f'Getting supported targets from {url}')

        resp = requests.get(
            url, headers={'User-Agent': Patchstorage.USER_AGENT})

        resp_data = Patchstorage.decode_json_response(resp)

        assert resp.status_code == 200, resp.content
        assert resp_data['targets'], f"Error: No targets field for platform {platform_id}"

        click.echo(
            f"Supported targets: {[t['slug'] for t in resp_data['targets']]}")

        return resp_data['targets']

    @staticmethod
    def upload_file(path: str, target_id: Optional[int] = None) -> str:
        """Upload a file to Patchstorage"""

        assert isinstance(path, str)
        assert isinstance(target_id, int) or target_id is None

        if Patchstorage.PS_API_TOKEN is None:
            raise PatchstorageException('Not authenticated')

        click.echo(f'Uploading: {path}')

        post_data: dict = {}

        if target_id is not None:
            post_data['target'] = target_id

        resp = requests.post(PS_API_URL + '/files', data=post_data, files={
            'file': open(path, 'rb')
        },
            headers={
            'Authorization': 'Bearer ' + Patchstorage.PS_API_TOKEN,
            'User-Agent': Patchstorage.USER_AGENT
        })

        resp_data = Patchstorage.decode_json_response(resp)

        if not resp.ok:
            raise PatchstorageException(
                f'Failed to upload file {path} {resp_data}')

        click.secho(
            f'Uploaded: {resp_data["filename"]} (ID:{resp_data["id"]})')

        return resp_data['id']

    @staticmethod
    def get(pid: Optional[str] = None, uids: Optional[list] = None) -> Optional[dict]:
        """Get a patch from Patchstorage by ID or UID"""

        if Patchstorage.PS_API_TOKEN is None:
            raise PatchstorageException('Not authenticated')

        if pid is None and uids is None:
            raise PatchstorageException(
                'Internal error - must provide ID or UID')

        if pid is not None:
            resp = requests.get(PS_API_URL + '/patches/' + str(pid),
                                headers={'User-Agent': Patchstorage.USER_AGENT})

            resp_data = Patchstorage.decode_json_response(resp)

            if not resp.ok:
                click.echo(resp.status_code)
                click.echo(resp.request)
                click.echo(resp_data)
                raise PatchstorageException(f'Failed to get plugin {str(pid)}')

            if resp_data.get('id') == pid:
                return resp_data

            raise PatchstorageException(f'Failed to get plugin {str(pid)}')

        if uids is not None:

            params: Dict[str, Union[int, list]] = {
                'uids[]': uids,
                'platforms[]': PS_LV2_PLATFORM_ID
            }

            resp = requests.get(PS_API_URL + '/patches/', params=params,
                                headers={'User-Agent': Patchstorage.USER_AGENT})

            resp_data = Patchstorage.decode_json_response(resp)

            if not resp.ok:
                click.echo(resp.status_code)
                click.echo(resp.request)
                click.echo(resp_data)
                raise PatchstorageException(
                    f'Failed to get plugin with uids {uids}')

            if isinstance(resp_data, list) and len(resp_data) > 0:
                if len(resp_data) > 1:
                    raise PatchstorageException(
                        f'Multiple plugins found with provided uids {uids}')

                resp = requests.get(PS_API_URL + '/patches/' + str(resp_data[0]['id']),
                                    headers={'User-Agent': Patchstorage.USER_AGENT})

                resp_data = Patchstorage.decode_json_response(resp)

                return resp_data

        return None

    @staticmethod
    def upload(folder: str, data: dict) -> dict:
        """Upload a patch to Patchstorage"""

        assert 'artwork' in data, 'Missing artwork field in patchstorage.json'
        assert 'files' in data, 'Missing files field in patchstorage.json'

        if Patchstorage.PS_API_TOKEN is None:
            raise PatchstorageException('Not authenticated')

        artwork_id = Patchstorage.upload_file(data['artwork'])

        file_ids: list = []

        for file in data['files']:
            file_id = Patchstorage.upload_file(
                file['path'], target_id=file.get('target_id'))
            file_ids.append(int(file_id))

        data['artwork'] = int(artwork_id)
        data['files'] = file_ids

        click.echo(f'Uploading: {folder}')

        resp = requests.post(PS_API_URL + '/patches', json=data, headers={
            'Authorization': 'Bearer ' + Patchstorage.PS_API_TOKEN,
            'User-Agent': Patchstorage.USER_AGENT
        })

        resp_data = Patchstorage.decode_json_response(resp)

        if not resp.ok:
            raise PatchstorageException(
                f'Failed to upload {folder} {resp_data}')

        return resp_data

    @staticmethod
    def update(folder: str, data: dict, pid: int) -> dict:
        """Update a patch on Patchstorage"""

        if Patchstorage.PS_API_TOKEN is None:
            raise PatchstorageException('Not authenticated')

        click.echo(f'Updating: {folder}')

        artwork_id = Patchstorage.upload_file(data['artwork'])

        file_ids: list = []

        for file in data['files']:
            file_id = Patchstorage.upload_file(
                file['path'], target_id=file.get('target_id'))
            file_ids.append(int(file_id))

        data['artwork'] = int(artwork_id)
        data['files'] = file_ids

        resp = requests.put(PS_API_URL + '/patches/' + str(pid), json=data, headers={
            'Authorization': 'Bearer ' + Patchstorage.PS_API_TOKEN
        })

        resp_data = Patchstorage.decode_json_response(resp)

        if not resp.ok:
            raise PatchstorageException(
                f'Failed to update {folder} {resp_data}')

        return resp_data

    @staticmethod
    def push(username: str, folder: str, auto: bool, force: bool) -> None:
        """Push a patch to Patchstorage"""

        with open(os.path.join(PATH_DIST, folder, 'patchstorage.json'), 'r', encoding='utf8') as file:
            data = json.loads(file.read())

        if 'uids' not in data or len(data['uids']) == 0:
            raise PatchstorageException(
                f'Missing/bad uids field in patchstorage.json for {folder}')

        uploaded = Patchstorage.get(uids=data['uids'])

        # not uploaded or was removed from Patchstorage
        if uploaded is None:
            click.echo(f'Processing: {folder}')

            if auto:
                result = Patchstorage.upload(folder, data)

            elif not click.confirm(f'(?): Upload {folder} (local-{data["revision"]})?'):
                return

            else:
                result = Patchstorage.upload(folder, data)

        # uploaded already
        else:

            # check if uploaded by same user
            if uploaded['author']['slug'].lower() == username.lower():
                # click.echo(f'{folder} was previously uploaded by you')
                pass
            else:
                click.secho(
                    f'Skip: {folder} already uploaded by {uploaded["author"]["slug"]} ({uploaded["url"]})', fg='yellow')
                return

            # if force, re-upload
            if force:
                result = Patchstorage.update(folder, data, uploaded['id'])

            # if auto, upload only if revision is different or not same targets
            elif auto:
                if uploaded['revision'] == data['revision'] and len(uploaded['files']) == len(data['files']):
                    click.echo(f'Skip: {folder} same version & targets')
                    return

                result = Patchstorage.update(folder, data, uploaded['id'])

            elif not click.confirm(f'(?): Update {folder} (local-ver:{data["revision"]}, cloud-ver:{uploaded["revision"]}, local-targets:{len(data["files"])}, cloud-targets:{len(uploaded["files"])})?'):
                return

            else:
                result = Patchstorage.update(folder, data, uploaded['id'])

        click.secho(
            f'Published: {result["url"]} (ID:{result["id"]})', fg='green')


class PluginManagerException(Exception):
    """PluginManager Exception"""


class PluginManager:
    """Plugin Manager class"""

    def __init__(self) -> None:
        assert PATH_ROOT
        assert PATH_PLUGINS
        assert PATH_DIST
        assert PS_LV2_PLATFORM_ID

        self.plugins_path = pathlib.Path(PATH_PLUGINS)
        self.dist_path = pathlib.Path(PATH_DIST)
        self.targets = Patchstorage.get_platform_targets(PS_LV2_PLATFORM_ID)
        self.licenses = self.load_json_data('licenses.json')
        self.categories = self.load_json_data('categories.json')
        self.overwrites = self.load_json_data('plugins.json')
        self.multi_bundles_map: dict = {}
        self._context: Optional[dict] = None

    @staticmethod
    def load_json_data(filename: str) -> dict:
        """Load JSON data from file"""

        try:
            path = PATH_ROOT / filename
            with open(path, "r", encoding='utf8') as file:
                return json.loads(file.read())
        except FileNotFoundError as err:
            raise PluginManagerException(
                f'Missing {filename} file in {PATH_ROOT}') from err
        except json.decoder.JSONDecodeError as err:
            raise PluginManagerException(
                f'Invalid JSON data in {filename}') from err

    @staticmethod
    def do_cleanup(path: pathlib.Path) -> None:
        """Cleanup directory"""

        assert isinstance(path, pathlib.Path), f'Invalid path type: {path}'

        if path.exists():
            try:
                shutil.rmtree(path)
            except OSError as err:
                raise PluginManagerException(
                    f'Failed to cleanup {path}') from err

        path.mkdir(parents=True, exist_ok=True)

    def get_bundle_overwrites(self, package_name) -> dict:
        """Get bundle overwrites from loaded plugins.json"""
        assert isinstance(self.overwrites, dict)

        return self.overwrites.get(package_name, {})

    def scan_plugins_directory(self) -> dict:
        """Scan plugins directory and return a dict with plugins info"""

        if not self.plugins_path.exists():
            raise PluginManagerException(
                f'Plugins directory not found: {PATH_PLUGINS}')

        click.echo(f"Supported targets: {[t['slug'] for t in self.targets]}")

        folders_found = [
            path for path in self.plugins_path.iterdir() if path.is_dir()]

        click.echo(f"Target folders found: {[str(f) for f in folders_found]}")

        candidates: dict = {}

        for target in self.targets:
            target_folder = self.plugins_path / target['slug']

            if not target_folder.exists():
                click.echo(
                    f'Warning: No folder found for target \'{target["slug"]}\'')
                continue

            for plugin_path in target_folder.iterdir():

                if not plugin_path.is_dir():
                    continue

                plugin_folder = plugin_path.parts[-1]

                if plugin_folder not in candidates:
                    candidates[plugin_folder] = []

                candidates[plugin_folder].append({
                    'slug': target['slug'],
                    'id': target['id'],
                    'path': plugin_path
                })

        click.echo(f"Total candidates: {len(candidates)}")
        click.echo(
            f"Total candidates builds: {sum([len(candidates[p]) for p in candidates])}")

        for package_name, targets_info in candidates.items():
            multi_bundle = PatchstorageMultiTargetBundle(
                package_name, targets_info)

            try:
                multi_bundle.validate_basic_files()
            except (BundleBadContents, PluginFieldMissing) as err:
                msg = f'Error: {err}'
                click.secho(msg, fg='red')
                continue

            self.multi_bundles_map[package_name] = multi_bundle

        return self.multi_bundles_map

    def get_multi_bundle(self, package_name: str) -> PatchstorageMultiTargetBundle:
        """Return a multi-bundle by package name"""

        if package_name not in self.multi_bundles_map:
            raise PluginManagerException(f'Bundle not found: {package_name}')
        return self.multi_bundles_map[package_name]

    def prepare_bundles(self) -> None:
        """Prepare bundles"""

        prepared = 0
        failed = 0

        for bundle in self.multi_bundles_map:
            done = self.prepare_bundle(self.multi_bundles_map[bundle])
            if done:
                prepared += 1
            else:
                failed += 1

        click.secho(f'Prepared: {prepared}', fg='green')
        click.secho(f'Failed: {failed}', fg='red')

    def prepare_bundle(self, multi_bundle: PatchstorageMultiTargetBundle) -> bool:
        """Prepare a bundle"""

        try:
            self._prepare_bundle(multi_bundle)
            return True
        except (BundleBadContents, PluginFieldMissing) as err:
            msg = f'Error: {err}'
            click.secho(msg, fg='red')
            return False

    def _prepare_bundle(self, multi_bundle: PatchstorageMultiTargetBundle) -> None:
        package_name = multi_bundle.package_name
        path_plugins_dist = self.dist_path / package_name
        path_ps_json = path_plugins_dist / 'patchstorage.json'
        path_data_json = path_plugins_dist / 'debug.json'
        path_screenshot = path_plugins_dist / 'artwork.png'

        click.echo(f'Processing: {multi_bundle.package_name}')

        multi_bundle.validate()

        bundle_overwrites = self.get_bundle_overwrites(
            multi_bundle.package_name)

        # patchstorage field validation happens here
        patchstorage_data = multi_bundle.get_patchstorage_data(
            platform_id=PS_LV2_PLATFORM_ID,
            licenses_map=self.licenses,
            categories_map=self.categories,
            overwrites=bundle_overwrites,
            default_tags=PS_TAGS_DEFAULT
        )

        self.do_cleanup(path_plugins_dist)

        if DEBUG:
            debug_path = multi_bundle.create_debug_json(path_data_json)
            click.echo(f'Debug: {debug_path}')

        artwork_path = multi_bundle.create_artwork(path_screenshot)
        click.echo(f'Created: {artwork_path}')

        tars_info = multi_bundle.create_tarballs(path_plugins_dist)
        click.echo(f'Created: {tars_info}')

        patchstorage_data['artwork'] = str(artwork_path)
        patchstorage_data['files'] = tars_info

        with open(path_ps_json, 'w', encoding='utf8') as file:
            file.write(json.dumps(patchstorage_data, indent=4))

        click.echo(f'Created: {path_ps_json}')
        click.secho(f'Prepared: {path_plugins_dist}', fg='green')

    @staticmethod
    def push_bundles(plugin_name: str, username: str, password: str, auto: bool, force: bool) -> None:
        """Pushes bundle(s) to Patchstorage.com"""

        Patchstorage.auth(username, password)

        if plugin_name != '':
            plugin_folder = PATH_DIST / plugin_name

            if not plugin_folder.exists():
                raise Exception(
                    f'Plugin {plugin_name} not found or not prepared')

            plugins_folders = [str(plugin_folder)]
        else:
            plugins_folders = os.listdir(PATH_DIST)

        for folder in plugins_folders:
            try:
                Patchstorage.push(username, folder, auto, force)
            except PatchstorageException as err:
                click.secho(f'Error: {err}', fg='red')
                continue


@click.group()
def cli() -> None:
    """Very basic utility for publishing LV2 plugins to Patchstorage.com"""


@cli.command()
@click.argument('plugin_name', type=str, required=True)
def prepare(plugin_name: str) -> None:
    """Prepare *.tar.gz and patchstorage.json files"""

    manager = PluginManager()
    manager.scan_plugins_directory()
    manager.do_cleanup(PATH_DIST)

    if plugin_name == 'all':
        manager.prepare_bundles()
    else:
        multi_bundle = manager.get_multi_bundle(plugin_name)
        manager.prepare_bundle(multi_bundle)


@cli.command()
@click.argument('plugin_name', type=str, required=True)
@click.option('--username', required=True, type=str, help='Patchstorage Username')
@click.password_option(help='Patchstorage Password', confirmation_prompt=False)
@click.option('--auto', is_flag=True, default=False)
@click.option('--force', is_flag=True, default=False)
def push(plugin_name: str, username: str, password: str, auto: bool, force: bool) -> None:
    """Publish plugins to Patchstorage"""

    if plugin_name == 'all':
        plugin_name = ''

    manager = PluginManager()
    manager.push_bundles(plugin_name, username, password, auto, force)


if __name__ == '__main__':

    try:
        cli()
    except (click.Abort, PluginManagerException) as e:
        click.secho(f'Error: {str(e)}', fg='red')
    except PatchstorageException as e:
        click.secho(f'Patchstorage Error: {str(e)}', fg='red')
    except requests.exceptions.ConnectionError as e:
        # TODO: handle this inside Patchstorage class
        click.secho(f'Patchstorage Error: {str(e)}', fg='red')
