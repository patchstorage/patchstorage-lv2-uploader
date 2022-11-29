from typing import Optional, Union, Dict
from copy import deepcopy
import os
import pathlib
import tarfile
import json
import requests
import urllib.parse
import shutil
import click
import pathlib
from lv2 import Bundle, MultiplePluginsDetected, PluginFieldMissing, BundleBadContents


PS_API_URL = 'https://patchstorage.com/api/beta'
PS_LV2_PLATFORM_ID = 8046
PS_LICENSES = None
PS_CATEGORIES = None
PS_SOURCES = None
PS_TARGETS = None
PS_TAGS_DEFAULT = ['lv2-plugin', ]
PATH_ROOT = pathlib.Path(__file__).parent.resolve()
PATH_PLUGINS = PATH_ROOT / 'plugins'
PATH_DIST = PATH_ROOT / 'dist'

# for dev purposes
if True:
    PS_API_URL = 'http://localhost/api/beta'
    PS_LV2_PLATFORM_ID = 5027



class PatchstorageMultiTargetBundle(Bundle):
    # TODO
    pass


class PatchstorageException(Exception):
    pass


class Patchstorage:

    PS_API_TOKEN = None

    @staticmethod
    def auth(username: str, password: str) -> None:
        assert PS_API_URL is not None
        assert username
        assert password

        url = PS_API_URL + '/auth/token'

        click.echo(f'Authenticating: {username} ({url})')

        r = requests.post(url, data={
            'username': username,
            'password': password
        }, headers={'User-Agent': 'patchbot-1.0'})

        if not r.ok:
            raise PatchstorageException('Failed to authenticate')

        Patchstorage.PS_API_TOKEN = r.json()['token']

    @staticmethod
    def get_platform_targets(platform_id: int) -> list:
        assert PS_API_URL is not None

        r = requests.get(f"{PS_API_URL}/platforms/{platform_id}")
        data = r.json()

        assert r.status_code == 200, r.content
        assert data['targets'], f"Error: No targets field for platform {platform_id}"

        return data['targets']

    @staticmethod
    def upload_file(path: str, target_id: int = None) -> str:
        assert isinstance(path, str)
        assert isinstance(target_id, int) or target_id is None

        if Patchstorage.PS_API_TOKEN is None:
            raise PatchstorageException('Not authenticated')

        click.echo(f'Uploading: {path}')

        data = {}

        if target_id is not None:
            data['target'] = target_id

        r = requests.post(PS_API_URL + '/files', data=data, files={
            'file': open(path, 'rb')
        },
            headers={
            'Authorization': 'Bearer ' + Patchstorage.PS_API_TOKEN,
            'User-Agent': 'patchbot-1.0'
        })

        if not r.ok:
            raise PatchstorageException(
                f'Failed to upload file {path} {r.json()}')

        return r.json()['id']

    @staticmethod
    def get(id: str = None, uids: list = None) -> Optional[dict]:
        if Patchstorage.PS_API_TOKEN is None:
            raise PatchstorageException('Not authenticated')

        if id is None and uids is None:
            raise PatchstorageException(
                'Internal error - must provide ID or UID')

        if id is not None:
            r = requests.get(PS_API_URL + '/patches/' + str(id),
                             headers={'User-Agent': 'patchbot-1.0'})

            if not r.ok:
                click.echo(r.status_code)
                click.echo(r.request)
                click.echo(r.json())
                raise PatchstorageException(f'Failed to get plugin {str(id)}')

            data = r.json()

            if data.get('id') == id:
                return data

        if uids is not None:

            params: Dict[str, Union[int, list]] = {
                'uids[]': uids,
                'platforms[]': PS_LV2_PLATFORM_ID
            }

            r = requests.get(PS_API_URL + '/patches/', params=params, headers={'User-Agent': 'patchbot-1.0'})

            if not r.ok:
                click.echo(r.status_code)
                click.echo(r.request)
                click.echo(r.json())
                raise PatchstorageException(f'Failed to get plugin with uids {uids}')

            data = r.json()

            if isinstance(data, list) and len(data) > 0:
                if len(data) > 1:
                    raise PatchstorageException(
                        f'Multiple plugins found with provided uids {uids}')
                return data[0]

        return None

    @staticmethod
    def upload(folder: str, data: dict) -> dict:
        assert 'artwork' in data, 'Missing artwork field in patchstorage.json'
        assert 'files' in data, 'Missing files field in patchstorage.json'

        if Patchstorage.PS_API_TOKEN is None:
            raise PatchstorageException('Not authenticated')

        artwork_id = Patchstorage.upload_file(data['artwork'])

        file_ids: list = []

        for file in data['files']:
            file_id = Patchstorage.upload_file(
                file['path'], target_id=file.get('target'))
            file_ids.append(int(file_id))

        data['artwork'] = int(artwork_id)
        data['files'] = file_ids

        click.echo(f'Uploading: {folder}')

        r = requests.post(PS_API_URL + '/patches', json=data, headers={
            'Authorization': 'Bearer ' + Patchstorage.PS_API_TOKEN,
            'User-Agent': 'patchbot-1.0'
        })

        if not r.ok:
            raise PatchstorageException(
                f'Failed to upload {folder} {r.json()}')

        return r.json()

    @staticmethod
    def update(folder: str, data: dict, id: int) -> dict:
        if Patchstorage.PS_API_TOKEN is None:
            raise PatchstorageException('Not authenticated')

        artwork_id = Patchstorage.upload_file(data['artwork'])

        file_ids: list = []

        for file in data['files']:
            file_id = Patchstorage.upload_file(
                file['path'], target_id=file.get('target'))
            file_ids.append(int(file_id))

        data['artwork'] = int(artwork_id)
        data['files'] = file_ids

        click.echo(f'Updating: {folder}')

        r = requests.put(PS_API_URL + '/patches/' + str(id), json=data, headers={
            'Authorization': 'Bearer ' + Patchstorage.PS_API_TOKEN
        })

        if not r.ok:
            raise PatchstorageException(
                f'Failed to update {folder} {r.json()}')

        return r.json()

    @staticmethod
    def push(username: str, folder: str, auto: bool, force: bool) -> None:

        with open(os.path.join(PATH_DIST, folder, 'patchstorage.json'), 'r') as f:
            data = json.loads(f.read())

        if 'uids' not in data or len(data['uids']) == 0:
            raise PatchstorageFieldMissing(
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

            # if auto, upload only if revision is different
            elif auto:
                if uploaded['revision'] == data['revision']:
                    click.echo(f'Skip: {folder} is up-to-date')
                    return

                result = Patchstorage.update(folder, data, uploaded['id'])

            elif not click.confirm(f'(?): Update {folder} (local-{data["revision"]} vs cloud-{uploaded["revision"]})?'):
                return

            else:
                result = Patchstorage.update(folder, data, uploaded['id'])

        click.secho(f'Published: {result["url"]} ({result["id"]})', fg='green')


class PatchstorageFieldMissing(Exception):
    pass


def load_json_data(filename: str) -> dict:
    try:
        path = os.path.join(PATH_ROOT, filename)
        with open(path, "r") as f:
            return json.loads(f.read())
    except FileNotFoundError:
        raise click.ClickException(f'Missing {filename} file in {PATH_ROOT}')


def get_license(license: str) -> str:
    assert PS_LICENSES is not None

    license = license.lower()

    inverted = {}
    for key, value in PS_LICENSES.items():
        for v in value:
            inverted[v.lower()] = key.lower()

    if license not in inverted:
        raise PatchstorageFieldMissing(f'Missing license slug for {license}')

    return int(inverted[license])


def get_category(cats: list) -> list:
    assert PS_CATEGORIES is not None

    inverted = {}
    for key, value in PS_CATEGORIES.items():
        for v in value:
            inverted[v] = key

    result = []
    for cat in cats:
        result.append(int(inverted[cat]))

    return list(set(result))


def get_source_url(folder: str) -> str:
    assert PS_SOURCES is not None

    inverted = {}
    for key, value in PS_SOURCES.items():
        for v in value:
            inverted[v] = key

    if folder not in inverted:
        raise PatchstorageFieldMissing(
            f'Missing "source_url" field for {folder}. Add it to sources.json')
        # click.echo(f'Warning: Missing "source_url" for {folder}')
        # return None

    return inverted[folder]


def get_state(stability: str) -> int:
    # 151 - ready-to-go
    # 150 - work-in-progress

    # if stability == 'testing':
    #     return 'work-in-progress'
    if stability == 'experimental':
        return 150
    return 151


def get_title(plugin: dict) -> str:
    if plugin.get('label'):
        return plugin['label']

    if plugin.get('name'):
        return plugin['name']

    raise PatchstorageFieldMissing(
        f'Missing title for {plugin["package_name"]}')


def get_data_for_patchstorage(bundle_data: dict) -> dict:
    assert isinstance(bundle_data, dict)
    assert 'plugins' in bundle_data
    assert len(bundle_data['plugins']) > 0

    folder = bundle_data['package_name']
    plugins = bundle_data['plugins']

    text = ''
    version = None
    license = ''
    platform = PS_LV2_PLATFORM_ID
    category: list = []
    tags: list = PS_TAGS_DEFAULT
    uids: list = []

    is_bundle = len(plugins) > 1

    name = None
    if is_bundle:
        name = f'{folder} Bundle'
    else:
        name = get_title(plugins[0])
        if len(name) < 5:
            name = f'{name} Plugin'

    for plugin in plugins:

        uids.append(plugin['uri'])

        if not license:
            license = plugin['license']
        else:
            if license != plugin['license']:
                raise Exception(
                    f'License mismatch in {folder} ({license} vs. {plugin["license"]})')

        for cat in plugin['category']:
            tag = cat.lower().replace(' ', '-')
            if tag not in tags:
                tags.append(tag)

            if cat not in category:
                category.append(cat)

        if version is None:
            version = plugin['version']
        else:
            if version != plugin['version']:
                version = max([version, plugin['version']])

        if is_bundle:
            text += f'Plugin: {get_title(plugin)}\n\n'

        if plugin.get('author', None):
            text += f'Credit: {plugin["author"]}\n\n'
        
        if plugin.get('comment') is None:
            text += 'No description available.\n\n\n'
        else:
            text += f'{plugin["comment"]}\n\n\n'

    license = get_license(license)
    category = get_category(category)
    source = get_source_url(folder)
    state = get_state(plugin['stability'])

    return {
        'uids': uids,
        'state': state,
        'platform': platform,
        'categories': category,
        'title': name,
        'content': text.strip(),
        'tags': tags,
        'revision': version,
        'license': license,
        'source_code_url': source
    }


def do_cleanup() -> None:
    if os.path.exists(PATH_DIST):
        try:
            shutil.rmtree(PATH_DIST)
        except OSError:
            raise Exception(f'Failed to cleanup {PATH_DIST}')
    os.mkdir(PATH_DIST)


def publish_plugins(plugin_name: str, username: str, password: str, auto: bool, force: bool) -> None:
    Patchstorage.auth(username, password)

    if plugin_name != '':
        plugin_folder = PATH_DIST / plugin_name
        
        if not plugin_folder.exists():
            raise Exception(f'Plugin {plugin_name} not found or not prepared')
        
        plugins_folders = [str(plugin_folder)]
    else:
        plugins_folders = os.listdir(PATH_DIST)

    for folder in plugins_folders:
        try:
            Patchstorage.push(username, folder, auto, force)
        except PatchstorageException as e:
            click.secho(f'Error: {str(e)}', fg='red')
            continue


def is_same_targets_files(targets: dict) -> bool:
    base_path = None
    basenames = None

    for _, path in targets.items():
        newnames = set([f.name for f in path.glob('**/*')])

        if basenames is None:
            base_path = path
            basenames = newnames
            continue

        if basenames != newnames:
            msg = f'Error: Found differences in {path} and {base_path}: {basenames ^ newnames}'
            click.secho(msg, fg='red')
            return False

        base_path = path
        basenames = newnames

    return True


def is_same_plugins_data(targets_data: dict) -> bool:
    base_data = None

    for _, bundle_data in targets_data.items():

        new_data = deepcopy(bundle_data)

        for plugin in new_data['plugins']:
            del plugin['screenshot']

        if base_data is None:
            base_data = new_data
            continue

        if sorted(base_data) != sorted(new_data):
            msg = 'Error: Found differences in plugins data'
            click.secho(msg, fg='red')
            return False

        base_data = new_data

    return True


def prepare_plugins_files(single_plugin_name: str = '') -> None:
    global PS_LICENSES
    global PS_CATEGORIES
    global PS_SOURCES
    global PS_TARGETS

    PS_LICENSES = load_json_data('licenses.json')
    PS_CATEGORIES = load_json_data('categories.json')
    PS_SOURCES = load_json_data('sources.json')
    PS_TARGETS = Patchstorage.get_platform_targets(PS_LV2_PLATFORM_ID)

    targets_map = {}
    for target in PS_TARGETS:
        targets_map[target['slug']] = target['id']

    # delete dist folder
    do_cleanup()

    plugins_dist_path = pathlib.Path(PATH_DIST)
    plugins_map = parse_plugins_dir(PS_TARGETS)

    if single_plugin_name:
        if single_plugin_name not in plugins_map:
            raise Exception(f'Plugin {single_plugin_name} not found')
        
        plugins_map = {single_plugin_name: plugins_map[single_plugin_name]}

    for plugin_name, targets in plugins_map.items():

        click.echo(f'Processing: {plugin_name}')

        # check folders contents
        if not is_same_targets_files(targets):
            click.secho(f'Skip: {plugin_name}', fg='yellow')
            continue

        path_plugins_dist = plugins_dist_path / plugin_name
        path_ps_json = path_plugins_dist / 'patchstorage.json'
        path_data_json = path_plugins_dist / 'debug.json'
        path_screenshot = path_plugins_dist / 'artwork.png'

        # parse plugins
        bundle_targets_store: dict = {}

        try:
            for target_name, target_path in targets.items():
                bundle = Bundle(target_path)
                bundle_data = bundle.parse()
                bundle_targets_store[target_name] = bundle_data

        except (MultiplePluginsDetected, PluginFieldMissing) as e:
            click.secho(f'Skip: {e} ({target_path})', fg='yellow')
            continue

        # check if all plugins have the same uri
        if not is_same_plugins_data(bundle_targets_store):
            click.secho(f'Skip: {plugin_name}', fg='yellow')
            continue

        try:
            plugin_ps_data = get_data_for_patchstorage(bundle_data)
        except (PatchstorageFieldMissing,) as e:
            click.secho(f'Skip: {e} {target_path}', fg='yellow')
            continue

        os.mkdir(path_plugins_dist)

        with open(path_data_json, 'w', encoding='utf8') as f:
            f.write(json.dumps(bundle_data, indent=4))

        click.echo(f'Created: {path_data_json}')

        shutil.copy2(bundle_data['plugins'][0]['screenshot'], path_screenshot)

        plugin_ps_data['artwork'] = str(path_screenshot)

        click.echo(f'Created: {path_screenshot}')

        files: list = []

        for target, path in targets.items():
            path_target_folder = path_plugins_dist / target

            os.mkdir(path_target_folder)

            path_target_tar = path_target_folder / f"{plugin_name}.tar.gz"

            with tarfile.open(path_target_tar, "w:gz") as tar:
                tar.add(path, arcname=plugin_name)

            click.echo(f'Created: {path_target_tar}')

            files.append({
                'target': targets_map[target],
                'path': str(path_target_tar),
            })

        plugin_ps_data['files'] = files

        with open(path_ps_json, 'w', encoding='utf8') as f:
            f.write(json.dumps(plugin_ps_data, indent=4))

        click.echo(f'Created: {path_ps_json}')
        click.secho(f'Prepared: {path_plugins_dist}', fg='green')


def parse_plugins_dir(targets: list) -> dict:
    click.echo(f"Supported targets: {[t['slug'] for t in targets]}")

    path_plugins = pathlib.Path(PATH_PLUGINS)

    folders_found = [path for path in path_plugins.iterdir() if path.is_dir()]
    click.echo(f"Target folders found: {[str(f) for f in folders_found]}")

    bundles_map: dict = {}

    for target in targets:
        target_folder = path_plugins / target['slug']

        if not target_folder.exists():
            click.echo(f'Warning: No folder found for {target["slug"]}')
            continue

        for plugin_folder in target_folder.iterdir():
            if not plugin_folder.is_dir():
                continue

            bundle = Bundle(plugin_folder)

            try:
                bundle.validate_files()
            except BundleBadContents as e:
                msg = f'Error: {e}'
                click.secho(msg, fg='red')
                continue

            if bundle.package_name not in bundles_map:
                bundles_map[bundle.package_name] = {}

            bundles_map[bundle.package_name][target['slug']] = bundle.path

    bundles_found = len(bundles_map)
    total_targets_found = sum([len(bundles_map[p]) for p in bundles_map])

    click.echo(f"Total bundles: {bundles_found}")
    click.echo(f"Total builds: {total_targets_found}")

    return bundles_map


@click.group()
def cli() -> None:
    """Very basic utility to help with publishing LV2 plugins to Patchstorage.com"""
    pass


@cli.command()
@click.argument('plugin_name', type=str, required=True)
def prepare(plugin_name: str) -> None:
    """Prepare *.tar.gz and patchstorage.json files"""
    
    if plugin_name == 'all':
        plugin_name = ''

    prepare_plugins_files(plugin_name)


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

    publish_plugins(plugin_name, username, password, auto, force)


if __name__ == '__main__':

    try:
        cli()
    except (click.Abort) as e:
        click.secho(f'Error: {str(e)}', fg='red')
