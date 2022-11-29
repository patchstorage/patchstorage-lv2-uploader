import json
from typing import Optional, Tuple, Union, Any, Optional, Iterator, Dict, List
from unittest.util import strclass
import rdflib
import pathlib

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
                path = path.replace('file:///', '')
            return pathlib.Path(path)
        return None

    def _triples(self, triple: list) -> Iterator[list]:
        root, predicate, obj = triple
        for root in self._list(root):
            for predicate in self._list(predicate):
                for obj in self._list(obj):
                    # type: ignore
                    for triple in self.graph.triples([root, predicate, obj]):  # type: ignore
                        yield triple

    def _list(self, item: Any) -> Union[tuple, list]:
        if isinstance(item, list) or isinstance(item, tuple):
            return item
        else:
            return [item]


class PluginFieldMissing(Exception):
    def __init__(self, field: str, folder: str):
        self.field = field
        self.folder = folder

    def __str__(self) -> str:
        return f'Plugin field "{self.field}" missing in {self.folder}'


class MultiplePluginsDetected(Exception):
    pass


class PluginBadManifest(Exception):
    pass


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
            if triple[2] == None:
                continue
            for triple in self._triples([triple[2], child, None]):
                return str(triple[2]).strip()
        return None

    def _get_type_field(self, predicate: rdflib.term.URIRef, ns: rdflib.namespace.Namespace = None) -> dict:
        data = {}
        for triple in self._triples([self.subject, predicate, None]):
            url = triple[2]
            if ns:
                if not url.startswith(ns):
                    continue
                url = url[len(ns):]
            data[url] = True
        return data

    def get_name(self) -> str:
        value = self._get_field(doap.name)
        if not value:
            raise PluginFieldMissing('name', self.package_name)
        return value

    def get_label(self) -> Optional[str]:
        return self._get_field(doap.label)

    def get_brand(self) -> Optional[str]:
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

    def get_license(self) -> str:
        # TODO: how to handle missing licenses?
        value = self._get_field(doap.license)
        if not value:
            raise PluginFieldMissing('license', self.package_name)
        # HACK: if license is linked as a file, get the filename
        if 'file:///' in value:
            path = self._parse_path(value)
            if path:
                if path.exists():
                    raise NotImplementedError('License file not supported')
                return path.parts[-1]
        return value

    def get_comment(self) -> Optional[str]:
        value = self._get_field(rdfschema.comment)
        return value

    def get_version(self) -> str:
        minor = self._get_field(lv2core.minorVersion)
        micro = self._get_field(lv2core.microVersion)

        minor_version = int(minor) if minor else 0
        micro_version = int(micro) if micro else 0

        return '%d.%d' % (minor_version, micro_version)

    def get_stability(self, version: str) -> str:
        minor, micro = map(int, list(version.split('.')))

        # 0.x is experimental
        if minor == 0:
            return 'experimental'
        # odd x.2 or 2.x is testing/development
        elif (minor % 2 != 0 or micro % 2 != 0):
            return 'testing'
        # otherwise it's stable
        return 'stable'

    def get_category(self) -> List[str]:
        data = self._get_type_field(rdfsyntax.type, ns=lv2core)
        data.update(self._get_type_field(rdfsyntax.type, ns=mod))
        # NOTE: og MOD solution - not all cats get added
        # for key, value in CATEGORY_MAP.items():
        #     if key in data:
        #         return value
        categories: List[str] = []
        for key in data:
            if key in CATEGORY_MAP:
                categories += CATEGORY_MAP[key]
        return list(set(categories))

    def get_author(self) -> Optional[str]:
        value = self._get_nested_field(doap.developer, foaf.name)
        if value:
            return value
        return self._get_nested_field(doap.maintainer, foaf.name)

    def get_screenshot(self) -> str:
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
            'name': self.get_name(),
            'label': self.get_label(),
            'brand': self.get_brand(),
            'screenshot': self.get_screenshot(),
            'license': self.get_license(),
            'comment': self.get_comment(),
            'version': self.get_version(),
            'stability': self.get_stability(self.get_version()),
            'category': self.get_category(),
            'author': self.get_author()
        }

        self._data = data
        return data


class BundleBadContents(Exception):
    pass


class Bundle(BaseParser):

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.package_name = path.parts[-1]
        self.graph = rdflib.ConjunctiveGraph()
        self.format = 'n3'
        self.parsed_files: dict = {}
        self.plugins: List[Plugin] = []
        self._data: Optional[dict] = None

    def validate_files(self) -> None:
        if not self.path.is_dir():
            raise BundleBadContents(f"Invalid folder name {self.package_name}")

        self.manifest_path = self.path / "manifest.ttl"

        if not self.manifest_path.exists():
            raise BundleBadContents(
                f"No manifest.ttl in folder {self.package_name}")

        # check if we have .so file
        if not self.manifest_path.glob('*.so'):
            raise BundleBadContents(
                f"No .so file in folder {self.package_name}")

    def parse(self) -> dict:

        self.validate_files()

        self._parse_ttl(self.path / 'manifest.ttl')

        self._data = {'package_name': self.package_name, 'plugins': []}

        # ensure only one plugin per folder
        for triple in self._triples([None, rdfsyntax.type, lv2core.Plugin]):
            plugin = Plugin(graph=self.graph,
                            subject=triple[0], package_name=self.package_name)
            plugin_data = plugin.parse()
            self.plugins.append(plugin)
            self._data['plugins'].append(plugin_data)

        if len(self.plugins) == 0:
            raise BundleBadContents(
                f"No plugin found in folder {self.package_name}")

        return self._data

    def _parse_ttl(self, path: Any) -> None:
        file_path = self._parse_path(path)

        if file_path is None:
            return

        if not file_path.exists():
            return

        if file_path in self.parsed_files:
            return

        self.parsed_files[file_path] = True

        self.graph.parse(file_path, format=self.format)

        
        for extension in self.graph.triples([None, rdfschema.seeAlso, None]):  # type: ignore
            try:
                self._parse_ttl(extension[2])
            except rdflib.plugins.parsers.notation3.BadSyntax as e:  # type: ignore
                bad_file_path = str(extension[2])
                if bad_file_path.endswith('manifest.ttl'):
                    raise PluginBadManifest(
                        f'Bad syntax {bad_file_path}')
                print(f"Bad syntax {bad_file_path} (ignored)")
