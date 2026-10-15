"""Species profiles separate supported gait categories from uncalibrated controls."""
from importlib.resources import files
import json
from .core import AssetError


def all_profiles() -> dict:
    return json.loads(files(__package__).joinpath('profiles/species.json').read_text())['species']


def get_profile(name: str) -> dict:
    aliases={'canadian_lynx':'canada_lynx','lynx':'canada_lynx','badger':'american_badger',
             'wolf':'gray_wolf','bison':'american_bison','black':'black_bear','bear':'grizzly',
             'duck':'mallard','raven':'common_raven','swan':'trumpeter_swan'}
    key=name.lower().replace(' ','_').replace('-','_')
    key=aliases.get(key,key)
    profiles=all_profiles()
    if key not in profiles:
        raise AssetError('Unknown species. Available: '+', '.join(profiles))
    p=profiles[key];p['id']=key
    return p
