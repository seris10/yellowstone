"""Offline landmark editing."""
from pathlib import Path
import json
import numpy as np
from .core import Skeleton


def write_review(asset,skeleton: Skeleton,path):
    # Unique points provide a clean orthographic cloud without shipping textures.
    points=np.unique(np.round(asset.vertices,5),axis=0)
    if len(points)>20000:points=points[np.linspace(0,len(points)-1,20000).astype(int)]
    payload={'rig':skeleton.to_dict(),'points':points.tolist(),'source':asset.metadata.get('source','mesh')}
    template=Path(__file__).with_name('review_template.html').read_text()
    text=json.dumps(payload,separators=(',',':')).replace('<','\\u003c')
    Path(path).write_text(template.replace('/*PAYLOAD*/',text))
