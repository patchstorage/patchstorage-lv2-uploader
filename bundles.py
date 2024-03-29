from typing import Optional, Union, Any, Iterator, Dict, List
import os
from platform import system
import json
import tarfile
from copy import deepcopy
import pathlib
import shutil
import rdflib


rdfschema = rdflib.Namespace('http://www.w3.org/2000/01/rdf-schema#')
rdfsyntax = rdflib.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#')
lv2core = rdflib.Namespace('http://lv2plug.in/ns/lv2core#')
doap = rdflib.Namespace('http://usefulinc.com/ns/doap#')
foaf = rdflib.Namespace('http://xmlns.com/foaf/0.1/')
mod = rdflib.Namespace('http://moddevices.com/ns/mod#')
modgui = rdflib.Namespace('http://moddevices.com/ns/modgui#')

CATEGORY_MAP = {
    'MIDIPlugin': ['MIDI'],
    'DistortionPlugin': ['Distortion'],
    'WaveshaperPlugin': ['Distortion', 'Waveshaper'],
    'DynamicsPlugin': ['Dynamics'],
    'SimulatorPlugin': ['Simulator'],
    'AmplifierPlugin': ['Dynamics', 'Amplifier'],
    'CompressorPlugin': ['Dynamics', 'Compressor'],
    'ControlVoltagePlugin': ['ControlVoltage'],
    'ExpanderPlugin': ['Dynamics', 'Expander'],
    'GatePlugin': ['Dynamics', 'Gate'],
    'LimiterPlugin': ['Dynamics', 'Limiter'],
    'FilterPlugin': ['Filter'],
    'AllpassPlugin': ['Filter', 'Allpass'],
    'BandpassPlugin': ['Filter', 'Bandpass'],
    'CombPlugin': ['Filter', 'Comb'],
    'EQPlugin': ['Filter', 'Equaliser'],
    'MultiEQPlugin': ['Filter', 'Equaliser', 'Multiband'],
    'ParaEQPlugin': ['Filter', 'Equaliser', 'Parametric'],
    'HighpassPlugin': ['Filter', 'Highpass'],
    'LowpassPlugin': ['Filter', 'Lowpass'],
    'GeneratorPlugin': ['Generator'],
    'ConstantPlugin': ['Generator', 'Constant'],
    'InstrumentPlugin': ['Generator', 'Instrument'],
    'OscillatorPlugin': ['Generator', 'Oscillator'],
    'ModulatorPlugin': ['Modulator'],
    'ChorusPlugin': ['Modulator', 'Chorus'],
    'FlangerPlugin': ['Modulator', 'Flanger'],
    'PhaserPlugin': ['Modulator', 'Phaser'],
    'ReverbPlugin': ['Reverb'],
    'SpatialPlugin': ['Spatial'],
    'SpectralPlugin': ['Spectral'],
    'PitchPlugin': ['Pitch Shifter', 'Spectral'],
    'DelayPlugin': ['Delay'],
    'UtilityPlugin': ['Utility'],
    'AnalyserPlugin': ['Utility', 'Analyser'],
    'ConverterPlugin': ['Utility', 'Converter'],
    'FunctionPlugin': ['Utility', 'Function'],
    'MixerPlugin': ['Utility', 'Mixer']
}


class BaseParser():

    def __init__(self) -> None:
        self.graph = rdflib.ConjunctiveGraph()

    # TODO: revisit
    @staticmethod
    def _parse_path(path: Union[str, pathlib.Path, None]) -> Optional[pathlib.Path]:
        if isinstance(path, pathlib.Path):
            return path
        if isinstance(path, str):
            if path.startswith('http'):
                return None
            if path.startswith('file:///'):
                if system() == 'Windows':
                    return pathlib.Path(path.replace('file:///', ''))
                return pathlib.Path(path.replace('file://', ''))
        return None

    def _triples(self, triple: list) -> Iterator[list]:
        root, predicate, obj = triple
        for root in self._list(root):
            for predicate in self._list(predicate):
                for obj in self._list(obj):
                    for triple in self.graph.triples([root, predicate, obj]):  # type: ignore
                        yield triple

    def _list(self, item: Any) -> Union[tuple, list]:
        if isinstance(item, list) or isinstance(item, tuple):
            return item
        else:
            return [item]


class PluginFieldMissing(Exception):
    def __init__(self, field: str, folder: str, reason: str = '') -> None:
        self.field = field
        self.folder = folder
        self.reason = reason

    def __str__(self) -> str:
        return f'Plugin field "{self.field}" missing in {self.folder} {self.reason}'.strip()


class PluginBadContents(Exception):
    pass


class Plugin(BaseParser):

    def __init__(self, graph: rdflib.ConjunctiveGraph, subject: rdflib.term.URIRef, package_name: str):
        self.graph: rdflib.ConjunctiveGraph = graph
        self.subject: rdflib.term.URIRef = subject
        self.uri: Optional[str] = None
        self.package_name = package_name
        self._data: Optional[dict] = None

    def _get_field(self, predicate: rdflib.term.URIRef) -> Optional[str]:
        for triple in self._triples([self.subject, predicate, None]):
            return str(triple[2]).strip()
        return None

    def _get_nested_field(self, predicate: rdflib.term.URIRef, child: rdflib.term.URIRef) -> Optional[str]:
        # plugin.subject None to cover plugins with info in child node
        for triple in self._triples([None, predicate, None]):
            if triple[2] is None:
                continue
            for triple in self._triples([triple[2], child, None]):
                return str(triple[2]).strip()
        return None

    def _get_type_field(self, predicate: rdflib.term.URIRef, namespace: rdflib.namespace.Namespace = None) -> dict:
        data = {}
        for triple in self._triples([self.subject, predicate, None]):
            url = triple[2]
            if namespace:
                if not url.startswith(namespace):
                    continue
                url = url[len(namespace):]
            data[url] = True
        return data

    def _get_name(self) -> str:
        value = self._get_field(doap.name)
        if not value:
            raise PluginFieldMissing('name', self.package_name)
        return value

    def _get_label(self) -> Optional[str]:
        return self._get_field(doap.label)

    def _get_brand(self) -> Optional[str]:
        value = self._get_field(mod.brand)
        if value:
            return value
        value = self._get_nested_field(doap.developer, foaf.name)
        if value:
            return value
        value = self._get_nested_field(doap.maintainer, foaf.name)
        if value:
            return value
        value = self._get_nested_field(modgui.gui, modgui.brand)
        if value:
            return value
        return None

    def _get_license(self) -> Optional[str]:
        # TODO: how to handle missing licenses?
        value = self._get_field(doap.license)
        # if not value:
        #     raise PluginFieldMissing('license', self.package_name)
        # HACK: if license is linked as a file, get the filename
        if value and 'file:///' in value:
            path = self._parse_path(value)
            if path:
                if path.exists():
                    raise NotImplementedError('License file not supported')
                return path.parts[-1]
        return value

    def _get_comment(self) -> Optional[str]:
        value = self._get_field(rdfschema.comment)
        return value

    def _get_version(self) -> str:
        minor = self._get_field(lv2core.minorVersion)
        micro = self._get_field(lv2core.microVersion)

        minor_version = int(minor) if minor else 0
        micro_version = int(micro) if micro else 0

        return '%d.%d' % (minor_version, micro_version)

    def _get_stability(self, version: str) -> str:
        minor, micro = map(int, list(version.split('.')))

        # 0.x is experimental
        if minor == 0:
            return 'experimental'
        # odd x.2 or 2.x is testing/development
        elif (minor % 2 != 0 or micro % 2 != 0):
            return 'testing'
        # otherwise it's stable
        return 'stable'

    def _get_category(self) -> List[str]:
        data = self._get_type_field(rdfsyntax.type, namespace=lv2core)
        data.update(self._get_type_field(rdfsyntax.type, namespace=mod))
        # NOTE: og MOD solution - not all cats get added
        # for key, value in CATEGORY_MAP.items():
        #     if key in data:
        #         return value
        categories: List[str] = []
        for key in data:
            if key in CATEGORY_MAP:
                categories += CATEGORY_MAP[key]
        return list(set(categories))

    def _get_author(self) -> Optional[str]:
        value = self._get_nested_field(doap.developer, foaf.name)
        if value:
            return value
        return self._get_nested_field(doap.maintainer, foaf.name)

    def _get_screenshot(self) -> str:
        path = self._parse_path(self._get_nested_field(
            modgui.gui, modgui.screenshot))

        if not path or not path.exists():
            raise PluginFieldMissing('screenshot', self.package_name)

        return str(path)

    def parse(self) -> dict:

        if self._data is None:
            self._data = self._parse_data()

        return self._data

    def _parse_data(self) -> dict:
        data: Dict[str, Union[str, list, None]] = {
            'uri': str(self.subject),
            'name': self._get_name(),
            'label': self._get_label(),
            'brand': self._get_brand(),
            'screenshot': self._get_screenshot(),
            'license': self._get_license(),
            'comment': self._get_comment(),
            'version': self._get_version(),
            'stability': self._get_stability(self._get_version()),
            'category': self._get_category(),
            'author': self._get_author()
        }

        self._data = data
        return data

    def get_uri(self) -> str:
        assert self._data is not None

        return str(self.subject)

    def get_title(self) -> str:
        assert self._data is not None

        if self._data.get('label'):
            return self._data['label']

        if self._data.get('name'):
            return self._data['name']

        raise PluginFieldMissing('title', self.package_name)

    def get_license(self) -> Optional[str]:
        assert self._data is not None

        return self._data.get('license')

    def get_state(self) -> int:
        assert self._data is not None

        # 151 - ready-to-go
        # 150 - work-in-progress

        # if stability == 'testing':
        #     return 'work-in-progress'
        if self._data.get('stability') == 'experimental':
            return 150
        return 151

    def get_revision(self) -> str:
        assert self._data is not None

        # HACK: ensure we have a version
        return self._data.get('version', '0.0')

    def get_author(self) -> Optional[str]:
        assert self._data is not None

        return self._data.get('author')

    def get_categories(self) -> list:
        assert self._data is not None

        return self._data.get('category', [])

    def get_comment(self) -> str:
        assert self._data is not None

        blacklist = ['…', '...']

        value = self._data.get('comment')

        if value in blacklist:
            value = None

        if not value:
            value = 'No description available.'

        return value

    def has_modgui(self) -> bool:
        assert self._data is not None
        # TODO: once we support non-modgui screenshots, update this
        return self._data.get('screenshot') is not None


class BundleBadContents(Exception):
    pass


class Bundle(BaseParser):

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.package_name = path.parts[-1]
        self.manifest_path = self.path / "manifest.ttl"
        self.graph = rdflib.ConjunctiveGraph()
        self.format = 'n3'
        self.parsed_files: dict = {}
        self.plugins: list = []
        self._data: Optional[dict] = None

    def raise_if_not_parsed(self) -> None:
        """Raises an exception if the bundle has not been parsed yet."""
        if self._data is None:
            raise BundleBadContents(f"Bundle {self.package_name} not parsed. Run parse() first.")

    @property
    def data(self) -> dict:
        """Returns the parsed data."""
        if self._data is None:
            raise BundleBadContents(f"Bundle {self.package_name} not parsed. Run parse() first.")
        return self._data

    def get_plugin_count(self) -> int:
        self.raise_if_not_parsed()

        return len(self.plugins)

    def is_multi_plugin_bundle(self) -> bool:
        return self.get_plugin_count() > 1

    def validate_files(self) -> None:
        if not self.path.is_dir():
            raise BundleBadContents(f"Invalid folder name {self.package_name}")

        if not self.manifest_path.exists():
            raise BundleBadContents(
                f"No manifest.ttl in folder {self.package_name}")

        # check if we have .so file
        if not list(self.path.glob('*.so')):
            raise BundleBadContents(
                f"No .so file in folder {self.package_name}")

    def parse(self) -> dict:

        self.validate_files()

        self._parse_ttl(self.manifest_path)

        bundle_data = {'package_name': self.package_name, 'plugins': []}

        # ensure only one plugin per folder
        for triple in self._triples([None, rdfsyntax.type, lv2core.Plugin]):
            plugin = Plugin(graph=self.graph,
                            subject=triple[0], package_name=self.package_name)
            plugin_data = plugin.parse()
            bundle_data['plugins'].append(plugin_data)
            self.plugins.append(plugin)

        if len(self.plugins) == 0:
            raise BundleBadContents(
                f"No plugin found in folder {self.package_name}")

        self._data = bundle_data

        return self._data

    def _parse_ttl(self, path: Any) -> None:
        file_path = self._parse_path(path)

        if file_path is None:
            print(f"Warning: Bad path {path}")
            return

        if not file_path.exists():
            print(f"Warning: File not found {file_path}")
            return

        if file_path in self.parsed_files:
            return

        self.parsed_files[file_path] = True

        self.graph.parse(file_path, format=self.format)

        # type: ignore
        for extension in self.graph.triples([None, rdfschema.seeAlso, None]):
            try:
                self._parse_ttl(extension[2])
            except rdflib.plugins.parsers.notation3.BadSyntax as err:  # type: ignore
                bad_file_path = str(extension[2])
                # don't allow bad syntax in manifest.ttl
                if bad_file_path.endswith('manifest.ttl'):
                    raise PluginBadContents(
                        f'Bad syntax {bad_file_path}') from err
                print(f"Warning: Bad syntax {bad_file_path} (ignored)")


class PatchstorageBundle(Bundle):

    def __init__(self, path: pathlib.Path, target_id: int, target_slug: str) -> None:
        super().__init__(path)
        self.target_id = target_id
        self.target_slug = target_slug
        self.dist_tar: Optional[dict] = None
        self.dist_artwork_path: Optional[pathlib.Path] = None

    def get_uids(self) -> List[str]:
        """Returns a list of bundle UIDs."""
        self.raise_if_not_parsed()

        return [p.get_uri() for p in self.plugins]

    def get_title(self) -> str:
        """Returns the bundle title."""
        self.raise_if_not_parsed()

        if self.get_plugin_count() == 1:
            plugin_title = self.plugins[0].get_title()

            # HACK: for short plugin names
            if len(plugin_title) < 5:
                return f'{plugin_title} Plugin'

            return plugin_title

        return f'{self.package_name} Bundle'

    def get_license_id(self, licenses_map: dict, overwrites: dict) -> int:
        self.raise_if_not_parsed()

        # check if all bundle plugin licenses are the same
        bundle_license = None
        for plugin in self.plugins:
            if bundle_license is not None:
                if bundle_license != plugin.get_license():
                    raise BundleBadContents(
                        f'License mismatch in {self.package_name} ({bundle_license} vs. {plugin.get_license()})')
            bundle_license = plugin.get_license()

        if bundle_license is None:
            if 'license' in overwrites:
                bundle_license = overwrites['license']

        if bundle_license is None:
            raise BundleBadContents(
                f'No license found for {self.package_name}')

        bundle_license = bundle_license.lower()

        if licenses_map is None:
            return bundle_license

        inverted = {}
        for lic_id, values in licenses_map.items():
            for value in values:
                inverted[value.lower()] = lic_id.lower()

        if bundle_license not in inverted:
            raise BundleBadContents(
                f'Missing license ID for {bundle_license}. Update licenses.json.')

        return int(inverted[bundle_license])

    def get_state_id(self) -> int:
        self.raise_if_not_parsed()

        all_states = [p.get_state() for p in self.plugins]

        if 150 in all_states:
            return 150

        return 151

    def get_revision(self) -> str:
        self.raise_if_not_parsed()

        return max([p.get_revision() for p in self.plugins])

    def get_source_code_url(self, overwrites: dict) -> Optional[str]:
        self.raise_if_not_parsed()

        if 'source_code_url' not in overwrites:
            raise BundleBadContents(
                f'Missing "source_code_url" for {self.package_name}. Update plugins.json')

        return overwrites['source_code_url']

    def get_donate_url(self, overwrites: dict) -> Optional[str]:
        self.raise_if_not_parsed()

        if 'donate_url' not in overwrites:
            raise BundleBadContents(
                f'Missing "donate_url" for {self.package_name}. Update plugins.json')

        return overwrites['donate_url']

    def get_category_ids(self, categories: dict, overwrites: dict) -> list:
        self.raise_if_not_parsed()

        cats: list = []

        if 'categories' in overwrites:
            cats.extend(overwrites['categories'])
        else:
            for plugin in self.plugins:
                cats.extend(plugin.get_categories())

        if len(cats) == 0:
            raise BundleBadContents(
                f'No categories found for {self.package_name}.')

        inverted = {}
        for cat_id, values in categories.items():
            for value in values:
                inverted[value] = cat_id

        result = []
        for cat in cats:
            if cat not in inverted:
                raise BundleBadContents(
                    f'Missing category ID for {cat}. Update categories.json.')
            result.append(int(inverted[cat]))

        return result

    def get_tags(self, default_tags: Optional[list], overwrites: dict) -> list:
        self.raise_if_not_parsed()

        tags: list = []

        if 'tags' in overwrites:
            tags.extend(overwrites['tags'])
        else:
            for plugin in self.plugins:
                for cat in plugin.get_categories():
                    tag = cat.lower().replace(' ', '-').strip()
                    if tag not in tags:
                        tags.append(tag)

        if default_tags is not None:
            tags.extend(default_tags)

        tags = [t.lower() for t in tags]

        # uploader spedific tags
        has_modgui = all(p.has_modgui() for p in self.plugins)
        if has_modgui:
            tags.append('modgui')

        return list(set(tags))

    def get_comment(self) -> str:
        """Returns bundle description."""
        self.raise_if_not_parsed()

        text = ''

        for plugin in self.plugins:

            title = plugin.get_title()
            author = plugin.get_author()
            comment = plugin.get_comment()

            if self.is_multi_plugin_bundle():
                text += f'Plugin: {title}\n\n'

            if comment:
                text += f'{comment}\n\n'

            if author:
                text += f'Credit: {author}\n\n\n'

        return text.strip()

    def create_artwork(self, target_path: pathlib.Path) -> pathlib.Path:
        """Copies the first plugin's screenshot to the target path."""
        self.raise_if_not_parsed()

        shutil.copyfile(self.data['plugins'][0]['screenshot'], target_path)
        self.dist_artwork_path = target_path

        return target_path

    def create_tarball(self, target_path: pathlib.Path) -> dict:
        """Creates a tarball of the bundle and returns a dict with the path and target_id."""
        self.raise_if_not_parsed()

        tar_folder_path = target_path / self.target_slug
        tar_path = tar_folder_path / f"{self.path.name}.tar.gz"

        os.mkdir(tar_folder_path)

        with tarfile.open(tar_path, 'w:gz') as tar:
            tar.add(str(self.path), arcname=self.path.name)

        self.dist_tar = {
            'path': str(tar_path),
            'target_id': self.target_id
        }

        return self.dist_tar

class PatchstorageMultiTargetBundle:

    def __init__(self, package_name: str, targets_info: list) -> None:
        self.package_name = package_name
        self.targets_info = targets_info
        self.bundles: List[PatchstorageBundle] = []

        for target in self.targets_info:
            self.bundles.append(PatchstorageBundle(
                pathlib.Path(target['path']),
                target_id=target['id'],
                target_slug=target['slug'])
            )

    def validate(self) -> None:
        self.validate_targets_files()
        self.parse_bundles()
        self.validate_targets_data()

    def parse_bundles(self) -> None:
        for bundle in self.bundles:
            bundle.parse()

    def validate_basic_files(self) -> bool:
        for bundle in self.bundles:
            bundle.validate_files()
        return True

    def validate_targets_files(self) -> bool:
        base_path = None
        base_names = None

        for bundle in self.bundles:
            new_names = set([f.name for f in bundle.path.glob('**/*')])

            if base_names is not None and base_names != new_names:
                msg = f'Found differences in {bundle.path} and {base_path}: {base_names ^ new_names}'
                raise BundleBadContents(msg)

            base_path = bundle.path
            base_names = new_names

        return True

    def validate_targets_data(self) -> bool:
        """Validate that all targets have the same files"""
        base_data = None

        for bundle in self.bundles:

            new_data = deepcopy(bundle.data)

            for plugin in new_data['plugins']:
                del plugin['screenshot']

            if base_data is None:
                base_data = new_data
                continue

            if sorted(base_data) != sorted(new_data):
                msg = f'Found differences in {bundle.path} data'
                raise BundleBadContents(msg)

            base_data = new_data

        return True

    def create_tarballs(self, target_path: pathlib.Path) -> List[dict]:
        tar_info: list = []
        for bundle in self.bundles:
            tar_info.append(bundle.create_tarball(target_path))
        return tar_info

    def get_patchstorage_data(self, platform_id: int, licenses_map: dict, categories_map: dict, overwrites: dict, default_tags: list) -> dict:
        assert len(self.bundles) > 0

        bundle = self.bundles[0]

        data = {
            'uids': bundle.get_uids(),
            'state': bundle.get_state_id(),
            'platform': platform_id,
            'categories': bundle.get_category_ids(categories_map, overwrites),
            'title': bundle.get_title(),
            'content': bundle.get_comment(),
            'tags': bundle.get_tags(default_tags, overwrites),
            'revision': bundle.get_revision(),
            'license': bundle.get_license_id(licenses_map, overwrites),
            'source_code_url': bundle.get_source_code_url(overwrites),
            'donate_url': bundle.get_donate_url(overwrites)
        }

        # Remove fields with None values
        for key in list(data):
            if data[key] is None:
                del data[key]

        return data

    def create_artwork(self, target_path: pathlib.Path) -> pathlib.Path:
        assert len(self.bundles) > 0
        return self.bundles[0].create_artwork(target_path)

    def create_debug_json(self, target_path: pathlib.Path) -> pathlib.Path:
        """Create a JSON file with all the data from the bundle"""
        assert len(self.bundles) > 0

        debug_data = {}

        for bundle in self.bundles:
            debug_data[bundle.target_slug] = bundle.data

        with open(target_path, 'w', encoding='utf8') as file:
            file.write(json.dumps(debug_data, indent=4))

        return target_path
