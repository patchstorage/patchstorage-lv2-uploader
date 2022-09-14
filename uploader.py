import os
import pathlib
import tarfile
import json
import requests
import shutil
import click


PS_API_URL = 'https://patchstorage.com/api/beta'
PS_PLATFORM_SLUG = 'lv2-rpi-arm32'
PS_LICENSES = None
PS_CATEGORIES = None
PS_SOURCES = None
IGNORE_DIRS = ['.mypy_cache', '.pytest_cache', '.tox', 'build', 'dist', 'venv']
PATH_ROOT = pathlib.Path(__file__).parent.resolve()
PATH_PLUGINS = os.path.join(PATH_ROOT, 'plugins')
PATH_BUILDS = os.path.join(PATH_ROOT, 'builds')


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
            raise click.ClickException('Failed to authenticate')

        Patchstorage.PS_API_TOKEN = r.json()['token']

    @staticmethod
    def upload_file(path: str) -> str:
        if Patchstorage.PS_API_TOKEN is None:
            raise click.ClickException('Not authenticated')

        click.echo(f'  Uploading file {path}')

        r = requests.post(PS_API_URL + '/files', data={
            'token': Patchstorage.PS_API_TOKEN
        }, files={
            'file': open(path, 'rb')
        },
            headers={
            'Authorization': 'Bearer ' + Patchstorage.PS_API_TOKEN,
            'User-Agent': 'patchbot-1.0'
        })

        if not r.ok:
            click.echo(r.status_code)
            click.echo(r.request.body)
            click.echo(r.json())
            raise Exception(f'Failed to upload file {path}')

        return r.json()['id']

    @staticmethod
    def get(id: str = None, uid: str = None) -> dict:
        if Patchstorage.PS_API_TOKEN is None:
            raise click.ClickException('Not authenticated')
        
        if id is None and uid is None:
            raise click.ClickException('Internal error - must provide ID or UID')
        
        if id is not None:
            r = requests.get(PS_API_URL + '/patches/' + str(id), headers={'User-Agent': 'patchbot-1.0'})

            if not r.ok:
                click.echo(r.status_code)
                click.echo(r.request.body)
                click.echo(r.json())
                raise Exception(f'Failed to get plugin {str(id)}')
            
            data = r.json()

            if data.get('id') == id:
                return data

        if uid is not None:
            r = requests.get(PS_API_URL + '/patches/', params={'platform': PS_PLATFORM_SLUG, 'uid': uid}, headers={'User-Agent': 'patchbot-1.0'})

            if not r.ok:
                click.echo(r.status_code)
                click.echo(r.request.body)
                click.echo(r.json())
                raise Exception(f'Failed to get plugin {uid}')
            
            data = r.json()

            if isinstance(data, list) and len(data) > 0 and data[0].get('uid') == uid:
                return data[0]

        return {}

    @staticmethod
    def upload(folder: str, data: dict) -> dict:
        if Patchstorage.PS_API_TOKEN is None:
            raise click.ClickException('Not authenticated')

        artwork_id = Patchstorage.upload_file(os.path.join(
            PATH_BUILDS, folder, 'screenshot.png'))
        file_id = Patchstorage.upload_file(os.path.join(
            PATH_BUILDS, folder, folder + '.tar.gz'))

        data['artwork'] = int(artwork_id)
        data['files'] = [int(file_id), ]

        click.echo(f'Uploading {folder}')

        r = requests.post(PS_API_URL + '/patches', json=data, headers={
            'Authorization': 'Bearer ' + Patchstorage.PS_API_TOKEN,
            'User-Agent': 'patchbot-1.0'
        })

        if not r.ok:
            click.echo(r.status_code)
            click.echo(r.request.body)
            click.echo(r.json())
            raise click.ClickException(f'Failed to upload {folder}')

        return r.json()

    @staticmethod
    def update(folder: str, data: dict, id: int) -> dict:
        if Patchstorage.PS_API_TOKEN is None:
            raise click.ClickException('Not authenticated')

        artwork_id = Patchstorage.upload_file(os.path.join(
            PATH_BUILDS, folder, 'screenshot.png'))

        file_id = Patchstorage.upload_file(os.path.join(
            PATH_BUILDS, folder, folder + '.tar.gz'))

        data['artwork'] = int(artwork_id)
        data['files'] = [int(file_id), ]

        click.echo(f'Updating {folder}')

        r = requests.put(PS_API_URL + '/patches/' + str(id), json=data, headers={
            'Authorization': 'Bearer ' + Patchstorage.PS_API_TOKEN
        })

        if not r.ok:
            click.echo(r.status_code)
            click.echo(r.request.body)
            click.echo(r.json())
            raise click.ClickException(f'Failed to update {folder}')

        return r.json()

    @staticmethod
    def push(username: str, folder: str, auto: bool, force: bool) -> None:

        with open(os.path.join(PATH_BUILDS, folder, 'patchstorage.json'), 'r') as f:
            data = json.loads(f.read())

        if 'uid' not in data:
            raise click.ClickException(f'Missing UID in patchstorage.json for {folder}')

        # check if plugin already uploaded
        uploaded = Patchstorage.get(uid=data['uid'])        

        # not uploaded or was removed from Patchstorage
        if 'id' not in uploaded:
            click.echo(f'{folder} not uploaded yet')

            if auto:
                result = Patchstorage.upload(folder, data)

            elif not click.confirm(f'(?) Upload {folder} (local-{data["revision"]})?'):
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
                click.echo(f'{folder} already uploaded by {uploaded["author"]["slug"]} ({uploaded["link"]}). SKIP')
                return

            # if force, re-upload
            if force:
                result = Patchstorage.update(folder, data, uploaded['id'])

            # if auto, upload only if revision is different
            elif auto:
                if uploaded['revision'] == data['revision']:
                    click.echo(f'{folder} is up-to-date. SKIP')
                    return
                
                result = Patchstorage.update(folder, data, uploaded['id'])

            elif not click.confirm(f'(?) Update {folder} (local-{data["revision"]} vs cloud-{uploaded["revision"]})?'):
                return
            
            else:
                result = Patchstorage.update(folder, data, uploaded['id'])

        click.echo(f'Published {result["link"]}')


class Device:

    @staticmethod
    def get_all_uris(url: str) -> list:
        uris = []
        
        try:
            r = requests.get(url + '/effect/list')
        except requests.exceptions.ConnectionError:
            raise click.ClickException('Failed to connect to mod-ui server')

        try:
            data = r.json()
        except json.decoder.JSONDecodeError:
            raise click.ClickException('Failed to parse mod-ui server response')

        if not isinstance(data, list) or len(data) == 0 or data[0].get('uri') is None:
            raise click.ClickException('Failed to parse mod-ui server response or 0 plugins found')

        for plugin in data:
            uris.append(plugin['uri'])
        
        return uris

    @staticmethod
    def get_single_uri(url: str, uri: str) -> dict:
        try:
            r = requests.get(url + '/effect/get', params={'uri': uri})
        except requests.exceptions.ConnectionError:
            raise click.ClickException('Failed to connect to mod-ui server')

        try:
            data = r.json()
        except json.decoder.JSONDecodeError:
            raise click.ClickException('Failed to parse mod-ui server response')
        
        if not isinstance(data, dict) or data.get('uri') is None:
            raise click.ClickException('Failed to parse mod-ui server response')
        
        return data


def get_plugins_paths() -> list:
    paths = []
    for file in os.listdir(PATH_PLUGINS):
        dir = os.path.join(PATH_PLUGINS, file)
        if file in IGNORE_DIRS:
            continue
        if not os.path.isdir(dir):
            continue
        paths.append(file)
    return paths


def extract_plugin_info(data: dict) -> dict:

    comment = data['comment']
    comment = '' if comment == '...' else comment.strip()

    info = {
        'uri': data['uri'].strip(),
        'brand': data['brand'].strip(),
        'name': data['name'].strip(),
        'label': data['label'].strip(),
        'license': data['license'].strip(),
        'comment': comment,
        'category': data['category'],
        'version': data['version'].strip(),
        'author': data['author'].get('name', '').strip(),
        'screenshot': data['gui']['screenshot'].replace('/usr/modep/lv2/', '').replace('/', '\\'),
        'stability': data['stability'],
    }

    return info

# TODO: way to extract ttl data directly from lv2 plugin files
def create_data_dump(url: str) -> None:
    try:
        assert url.startswith('http://')
    except AssertionError:
        raise click.BadParameter('Provided --url is not a valid URL')

    url = url.rstrip('/')

    click.echo(f'Creating data.json dump from {url}')

    validated: dict = {}

    uris = Device.get_all_uris(url)
    paths = get_plugins_paths()
    
    for uri in uris:
        click.echo(f'Processing {uri}')
        data = Device.get_single_uri(url, uri)
        folder = data['bundles'][0].split('/')[-2]

        # no plugin files - skip
        if folder not in paths:
            continue

        if len(data['bundles']) > 1:
            click.echo(f'More than one bundle for {uri}. SKIP')
            continue

        if folder not in validated:
            validated[folder] = []

        info = extract_plugin_info(data)

        validated[folder].append(info)

    path = os.path.join(PATH_ROOT, 'data.json')

    with open(path, "w") as f:
        f.write(json.dumps(validated, indent=4))
    
    click.echo(f'Dump created in {path}')

# TODO: sqlite
def save_db_dump(data: dict) -> None:
    with open(os.path.join(PATH_ROOT, 'maintainers.json'), "w") as f:
        f.write(json.dumps(data, indent=4))

def load_json_data(filename: str) -> dict:
    try:
        path = os.path.join(PATH_ROOT, filename)
        with open(path, "r") as f:
            return json.loads(f.read())
    except FileNotFoundError:
        raise click.Abort(f'Missing {filename} file in {PATH_ROOT}')

def get_license(license: str) -> str:
    assert PS_LICENSES is not None

    inverted = {}
    for key, value in PS_LICENSES.items():
        for v in value:
            inverted[v] = key

    if license not in inverted:
        raise Exception(f'Missing license slug for {license}')

    return inverted[license]

# TODO: fix map in categories.json, additional patchstorage categories possible
def get_category(cats: list) -> list:
    assert PS_CATEGORIES is not None

    inverted = {}
    for key, value in PS_CATEGORIES.items():
        for v in value:
            inverted[v] = key

    result = []
    for cat in cats:
        result.append(inverted[cat])

    return result

# TODO: better approach is needed
def get_source_url(folder: str) -> str:
    assert PS_SOURCES is not None

    inverted = {}
    for key, value in PS_SOURCES.items():
        for v in value:
            inverted[v] = key

    if folder not in inverted:
        raise click.ClickException(f'Missing source url for {folder}')

    return inverted[folder]

def get_state(stability: str) -> str:
    # if stability == 'testing':
    #     return 'work-in-progress'
    if stability == 'experimental':
        return 'work-in-progress'
    return 'ready-to-go'

# TODO: template renderer for text?
def get_data_for_patchstorage(folder: str, plugins: list) -> dict:
    assert isinstance(plugins, list)
    assert len(plugins) > 0

    platform = PS_PLATFORM_SLUG
    category: list = []
    name = None
    text = ''
    tags = ['lv2', 'modgui', 'rpi-arm32']
    version = None
    license = None

    is_bundle = len(plugins) > 1
    is_first = True

    if is_bundle:
        name = f'Plugin Bundle {folder}'
        text += f'Plugin Bundle {folder}\n'

    if is_bundle:
        text += '\n'

    for plugin in plugins:

        if is_first:
            if plugin.get('author', None) is not None:
                text += f'Credit: {plugin["author"]}\n\n'
            is_first = False

        if version is None:
            version = plugin['version']
        else:
            if version != plugin['version']:
                version = max([version, plugin['version']])

        if license is None:
            license = plugin['license']
        else:
            if license != plugin['license']:
                raise Exception('License mismatch in ' + folder)

        for cat in plugin['category']:
            if cat not in category:
                category.append(cat)

        for cat in plugin['category']:
            tag = cat.lower().replace(' ', '-')
            if tag not in tags:
                tags.append(tag)

        if name is None:
            name = f"{plugin['label']}"

        if is_bundle:
            text += f"Plugin: {plugin['label']}\n"

        text += f'{plugin["comment"]}\n\n'

    if license is None:
        raise Exception('No license found in ' + folder)

    license = get_license(license)
    category = get_category(category)
    source = get_source_url(folder)
    state = get_state(plugins[0]['stability'])
    uid = plugins[0]['uri']

    return {
        'uid': uid,
        'state': state,
        'platform': platform,
        'categories': category,
        'title': name,
        'content': text,
        'tags': tags,
        'revision': version,
        'license': license,
        'source_code_url': source
    }


def do_cleanup() -> None:
    if os.path.exists(PATH_BUILDS):
        try:
            shutil.rmtree(PATH_BUILDS)
        except OSError:
            raise Exception(f'Failed to cleanup {PATH_BUILDS}')
    os.mkdir(PATH_BUILDS)


def push(username: str, password: str, auto: bool, force: bool) -> None:
    Patchstorage.auth(username, password)

    for folder in os.listdir(PATH_BUILDS):
        Patchstorage.push(username, folder, auto, force)


def build_plugins() -> None:
    data = load_json_data('data.json')

    do_cleanup()

    click.echo(f'{len(os.listdir(PATH_PLUGINS))} plugins candidates found')

    for folder in os.listdir(PATH_PLUGINS):

        absolute_path = os.path.join(PATH_PLUGINS, folder)

        if not os.path.isdir(absolute_path):
            continue

        click.echo(folder)
    
        if not folder.endswith('.lv2'):
            click.echo(f'Skipping {folder} (no .lv2 suffix)')
            continue

        contents = os.listdir(absolute_path)
        
        if 'manifest.ttl' not in contents:
            raise click.ClickException(f'Missing manifest.ttl in {folder} folder')

        if 'modgui.ttl' not in contents and 'modgui' not in contents:
            raise click.ClickException(f'Missing manifest.ttl in {folder} folder')

        if folder not in data:
            raise click.ClickException(f'Missing data for {folder} in data.json')

        plugins = data[folder]

        if len(plugins) < 1:
            raise click.ClickException(f'No plugins data found for {folder} in data.json')

        if len(plugins) > 1:
            raise click.ClickException(f'More than 1 plugin is bundled in {folder} - currently, bundles are not supported')

        ps_data = get_data_for_patchstorage(folder, plugins)

        build_dir = os.path.join(PATH_BUILDS, folder)
        os.mkdir(build_dir)

        json_path = os.path.join(build_dir, 'patchstorage.json')

        with open(json_path, 'w', encoding='utf8') as f:
            f.write(json.dumps(ps_data, indent=4))

        click.echo(f'  {json_path}')

        screenshot_path = os.path.join(build_dir, 'screenshot.png')

        shutil.copy2(os.path.join(PATH_PLUGINS, plugins[0]['screenshot']), screenshot_path)

        click.echo(f'  {screenshot_path}')

        tar_dir = os.path.join(build_dir, folder + ".tar.gz")
        with tarfile.open(tar_dir, "w:gz") as tar:
            tar.add('plugins/' + folder, arcname=folder)
        
        click.echo(f'  {tar_dir}')


@click.group()
def cli() -> None:
    """Very basic utility to help with publishing multiple LV2 plugins to Patchstorage.com"""
    pass


@cli.command()
@click.option('--url', required=True, type=str, help='mod-ui url')
def dump(url: str) -> None:
    """Dump plugin data from 'mod-ui' API (--url)"""
    create_data_dump(url)


@cli.command()
def generate() -> None:
    """Generate *.tar.gz and patchstorage.json files"""
    build_plugins()


@cli.command()
@click.option('--username', required=True, type=str, help='Patchstorage Username')
@click.password_option(help='Patchstorage Password', confirmation_prompt=False)
@click.option('--auto', is_flag=True, default=False)
@click.option('--force', is_flag=True, default=False)
def publish(username: str, password: str, auto: bool, force: bool) -> None:
    """Publish plugins to Patchstorage"""
    push(username, password, auto, force)


if __name__ == '__main__':

    try:
        PS_LICENSES = load_json_data('licenses.json')
        PS_CATEGORIES = load_json_data('categories.json')
        PS_SOURCES = load_json_data('sources.json')

        cli()
    except click.Abort as e:
        click.echo(f'Error: {str(e)}')
