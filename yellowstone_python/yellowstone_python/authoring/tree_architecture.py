"""Seeded conifer branch graphs and needle-shoot display rules."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import random

SOURCES = [
    {"id": "boudon_lpy", "citation": "Boudon et al. (2012), doi:10.3389/fpls.2012.00076", "url": "https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2012.00076/full", "supports": "Rooted growth-unit graphs and stochastic lateral productions", "transfer_scope": "Computational method; species-specific numerical parameters remain authored"},
    {"id": "usda_silvics", "citation": "Lotan and Critchfield (1990)", "url": "https://research.fs.usda.gov/silvics/lodgepole-pine", "supports": "Low stem taper, small limbs, poor natural pruning, shade intolerance", "transfer_scope": "Qualitative Pinus contorta botanical context"},
    {"id": "usda_needles", "citation": "USDA Forest Service lodgepole identification guide", "url": "https://www.fs.usda.gov/Internet/FSE_DOCUMENTS/fseprd1178128.pdf", "supports": "Two-needle fascicles and 1-3 inch needle lengths", "transfer_scope": "Needle morphology"},
]

@dataclass(frozen=True)
class ArchitectureParameters:
    whorl_spacing_m: float = 0.30
    spacing_relative_variation: float = 0.35
    branch_count_min: int = 4
    branch_count_max: int = 7
    branch_azimuth_jitter_rad: float = 0.20
    branch_length_fraction_min: float = 0.65
    branch_length_fraction_max: float = 1.0
    lower_branch_survival: float = 0.86
    branch_drop_fraction: float = 0.12
    branch_tip_turn_fraction: float = 0.50
    apex_taper_length_m: float = 1.25
    lateral_pairs_min: int = 3
    lateral_pairs_max: int = 5
    shoot_length_min_m: float = 0.24
    shoot_length_max_m: float = 0.44
    shoot_count_min: int = 2
    shoot_count_max: int = 3
    trunk_sway_fraction: float = 0.003
    needle_length_m: float = 0.0508
    fascicle_count: int = 2

    def validate(self):
        """Check finite geometry values and bounded display distributions."""
        values = asdict(self)
        if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in values.values()):
            raise ValueError("architecture parameters require finite numeric values")
        for low, high in [("branch_count_min", "branch_count_max"), ("lateral_pairs_min", "lateral_pairs_max"), ("shoot_count_min", "shoot_count_max")]:
            if any(not isinstance(values[x], int) for x in [low, high]) or not 1 <= values[low] <= values[high] <= 16:
                raise ValueError("architecture counts require ordered integers in [1,16]")
        if not 0 < self.whorl_spacing_m <= 5 or not 0 <= self.spacing_relative_variation < 0.8:
            raise ValueError("whorl spacing or variation is outside display bounds")
        if not 0 < self.apex_taper_length_m <= 5:
            raise ValueError("apex taper requires a positive length up to five meters")
        if not 0 <= self.lower_branch_survival <= 1 or not 0 <= self.trunk_sway_fraction <= 0.01:
            raise ValueError("survival or trunk sway is outside display bounds")
        if not 0 < self.branch_length_fraction_min <= self.branch_length_fraction_max <= 1:
            raise ValueError("branch fractions require 0 < min <= max <= 1")
        if not 0 < self.shoot_length_min_m <= self.shoot_length_max_m <= 1:
            raise ValueError("shoot lengths require ordered positive meters")
        if not 0.0254 <= self.needle_length_m <= 0.0762 or self.fascicle_count != 2:
            raise ValueError("lodgepole morphology requires paired 1-3 inch needles")
        if any(not 0 <= values[x] <= 0.5 for x in ["branch_drop_fraction", "branch_tip_turn_fraction", "branch_azimuth_jitter_rad"]):
            raise ValueError("branch curvature or angle is outside display bounds")


def _seed(identity, part):
    """Return a process-independent seed from an identity and graph component."""
    return int.from_bytes(hashlib.sha256(f"{identity}:{part}".encode("utf8")).digest()[:8], "big")


def _unit(v):
    """Normalize a nonzero vector."""
    length = math.sqrt(sum(x*x for x in v))
    if length <= 1e-12:
        raise ValueError("branch direction requires nonzero length")
    return [x / length for x in v]


def _add(a, b, fraction=1):
    """Return the translated point."""
    return [x + fraction*y for x,y in zip(a,b)]


def _point(axis, fraction):
    """Interpolate a piecewise-linear branch axis."""
    if not isinstance(fraction,(int,float)) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("axis interpolation requires a finite fraction in [0,1]")
    points = axis["points_m"]
    index = fraction * (len(points)-1)
    left = min(len(points)-2, int(index))
    return [a+(b-a)*(index-left) for a,b in zip(points[left],points[left+1])]



def stem_radius_m(height_m, dbh_m, y_m):
    """Return an authored stem taper that preserves DBH at 1.3 m."""
    values = [height_m,dbh_m,y_m]
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in values):
        raise ValueError("stem dimensions require finite numeric values")
    if height_m <= 1.3 or dbh_m <= 0 or not 0 <= y_m <= height_m:
        raise ValueError("stem radius requires height above breast height and a valid stem elevation")
    radius = dbh_m / 2 * ((height_m-y_m)/(height_m-1.3))**.85
    butt = dbh_m * .10 * (math.exp(-y_m/.5)-math.exp(-1.3/.5))
    return max(min(.002,dbh_m*.05), radius+butt)

def generate_architecture(dimensions, identity, parameters=None):
    """Build connected branch axes and terminal needle-shoot records in meters."""
    parameters = parameters or ArchitectureParameters()
    parameters.validate()
    h, dbh, r, ratio = (dimensions[k] for k in ["height_m","dbh_m","crown_radius_m","crown_ratio"])
    if any(isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) for x in [h,dbh,r,ratio]):
        raise ValueError("tree dimensions require finite numeric values")
    if h <= 1.3 or dbh <= 0 or r <= 0 or not 0 <= ratio <= 1:
        raise ValueError("tree dimensions require positive H, DBH and radius, and crown ratio in [0,1]")
    base=h*(1-ratio)
    phases=[0.37,1.7]
    def trunk(y):
        offset=parameters.trunk_sway_fraction*h*(y/h)**4
        return [offset*math.sin(y/h*4+phases[0]),y,offset*math.sin(y/h*3+phases[1])]
    stem={"id":"stem","parent_id":None,"order":0,"points_m":[trunk(h*i/20) for i in range(21)],"radius_base_m":stem_radius_m(h,dbh,0.0),"radius_at_breast_height_m":dbh/2,"radius_profile_m":[[y,stem_radius_m(h,dbh,y)] for y in sorted({h*i/20 for i in range(21)}|{1.3})],"radius_class":"authored_taper_preserving_dbh","alive":True}
    axes=[stem]; shoots=[];whorls=[]
    live_length=h*ratio if ratio else h*.7
    count=max(3, min(80,round(live_length/parameters.whorl_spacing_m)))
    rng=random.Random(_seed(identity,"whorls"))
    weights=[rng.uniform(1-parameters.spacing_relative_variation,1+parameters.spacing_relative_variation) for _ in range(count+1)]
    total=sum(weights);fraction=0;rotation=rng.uniform(0,math.tau)
    for level,weight in enumerate(weights[:-1]):
        fraction += weight/total
        y=base+fraction*live_length if ratio else h*(.20+.7*fraction)
        apex_scale=min(1., max(.03, (h-y)/parameters.apex_taper_length_m)) if ratio else 1.
        whorl_rng=random.Random(_seed(identity,f"whorl:{level}"))
        n=whorl_rng.randint(parameters.branch_count_min,parameters.branch_count_max)
        rotation += whorl_rng.uniform(.35,1.45)
        whorls.append({"id":level,"height_m":y,"candidate_branches":n,"evidence_class":"authored"})
        for slot in range(n):
            branch_rng=random.Random(_seed(identity,f"branch:{level}:{slot}"))
            survival=parameters.lower_branch_survival+(1-parameters.lower_branch_survival)*fraction
            alive=bool(ratio) and branch_rng.random()<survival
            az=rotation+slot*math.tau/n+branch_rng.uniform(-parameters.branch_azimuth_jitter_rad,parameters.branch_azimuth_jitter_rad)
            radial=[math.cos(az),0,math.sin(az)];side=[-radial[2],0,radial[0]]
            length=r*(1-fraction)**.90*branch_rng.uniform(parameters.branch_length_fraction_min,parameters.branch_length_fraction_max)
            length *= apex_scale
            if not alive:
                if branch_rng.random() < .55:
                    continue
                length *= branch_rng.uniform(.08, .38)
            start=_point(stem,(y+branch_rng.uniform(-.32,.32)*parameters.whorl_spacing_m)/h)
            points=[]
            for i in range(6):
                u=i/5
                vertical=length*(-parameters.branch_drop_fraction*math.sin(math.pi*u)+parameters.branch_tip_turn_fraction*u**3+fraction*.12*u)
                points.append(_add(_add(start,radial,length*u),[0,vertical,0]))
            branch={"id":f"b{level}_{slot}","parent_id":"stem","attachment_m":start,"attachment_fraction":start[1]/h,"order":1,"points_m":points,"radius_base_m":dbh*(.045+.035*(1-fraction)),"alive":alive,"whorl_id":level}
            axes.append(branch)
            if not alive: continue
            pairs=branch_rng.randint(parameters.lateral_pairs_min,parameters.lateral_pairs_max)
            for lateral in range(pairs):
                u=.20+.70*(lateral+.5)/pairs
                attachment=_point(branch,u)
                for sign in [-1,1]:
                    d=_unit(_add(_add([0,branch_rng.uniform(.18,.65),0],radial,.60),side,sign*.72))
                    size=max(.09*apex_scale,length*(1-u)*branch_rng.uniform(.35,.55))
                    tip=_add(attachment,d,size)
                    axis={"id":branch['id']+f"_l{lateral}_{sign}","parent_id":branch['id'],"order":2,"attachment_fraction":u,"attachment_m":attachment,"points_m":[attachment,_add(attachment,d,size*.5),tip],"radius_base_m":.004,"alive":True}
                    axes.append(axis)
                    for shoot in range(branch_rng.randint(parameters.shoot_count_min,parameters.shoot_count_max)):
                        fraction_s=.22+.78*(shoot+.5)/parameters.shoot_count_max
                        p=_point(axis,fraction_s)
                        direction=_unit(_add(_add([0,branch_rng.uniform(.55,1.05),0],d,.8),side,branch_rng.uniform(-.28,.28)))
                        shoot_length=branch_rng.uniform(parameters.shoot_length_min_m,parameters.shoot_length_max_m)*apex_scale
                        shoot_length=min(shoot_length, max(.025, (h-.06-p[1])/direction[1]))
                        shoots.append({"id":axis['id']+f"_s{shoot}","parent_id":axis['id'],"attachment_fraction":fraction_s,"base_m":p,"tip_m":_add(p,direction,shoot_length),"direction":direction,"length_m":shoot_length,"needle_length_m":parameters.needle_length_m,"fascicle_count":2,"evidence_class":"authored"})
    if ratio:
        for index in range(7):
            y = h - .08 - index * .11
            fraction_s = y / h
            p = _point(stem, fraction_s)
            az = index * 2.399963
            direction = _unit([.20 * math.cos(az), 1., .20 * math.sin(az)])
            length = min(.30, h - y)
            shoots.append({"id": f"leader_s{index}", "parent_id": "stem",
                           "attachment_fraction": fraction_s, "base_m": p,
                           "tip_m": _add(p, direction, length), "direction": direction,
                           "length_m": length, "needle_length_m": parameters.needle_length_m,
                           "fascicle_count": 2, "evidence_class": "authored"})
    result={"schema":"yellowstone.tree_architecture.v1","identity":str(identity),"dimensions_m":dict(dimensions),"parameters":asdict(parameters),"axes":axes,"shoots":shoots,"whorls":whorls,"sources":SOURCES,"evidence_class":"authored","evidence_basis":"literature_computational_method_and_authored_display_parameters","status":"illustrative_not_locally_validated","uncertainty":"unknown","parameter_distributions":"Bounded authored display distributions; local population distributions unknown","limitations":["Whorl station count does not establish age or annual growth.","Branch survival is an authored display rule; local light and mortality are unmeasured.","Needle shoots approximate occupied foliage volume; no calibrated leaf area or biomass.","Dimensions retain their caller-provided source classes."]}
    validate_architecture(result)
    return result


def validate_architecture(graph):
    """Check unique connected axes and finite shoot attachment geometry."""
    axes={axis['id']:axis for axis in graph['axes']}
    if len(axes)!=len(graph['axes']) or list(axes)[0]!='stem': raise ValueError('axes require unique IDs and a stem root')
    for axis in axes.values():
        points=axis['points_m']
        if len(points)<2 or any(len(p)!=3 or any(not math.isfinite(x) for x in p) for p in points): raise ValueError('axis geometry requires finite 3D points')
        if axis['order']>0:
            if axis['parent_id'] not in axes or axes[axis['parent_id']]['order']!=axis['order']-1: raise ValueError('axis parent order is invalid')
            anchor=axis['attachment_m']
            if any(abs(a-b)>1e-9 for a,b in zip(anchor,points[0])): raise ValueError('axis is disconnected from its anchor')
            parent_anchor = _point(axes[axis['parent_id']], axis['attachment_fraction'])
            if any(abs(a-b)>1e-9 for a,b in zip(anchor,parent_anchor)): raise ValueError('axis anchor differs from its parent')
    for shoot in graph['shoots']:
        if shoot['parent_id'] not in axes or not axes[shoot['parent_id']]['alive']: raise ValueError('shoot requires a live axis')
        if not all(math.isfinite(x) for k in ['base_m','tip_m','direction'] for x in shoot[k]): raise ValueError('shoot geometry requires finite vectors')
        parent_anchor = _point(axes[shoot['parent_id']], shoot['attachment_fraction'])
        if any(abs(a-b)>1e-9 for a,b in zip(shoot['base_m'],parent_anchor)): raise ValueError('shoot anchor differs from its parent')
        if abs(sum(x*x for x in shoot['direction'])-1)>1e-9: raise ValueError('shoot direction requires unit length')

BECHTOLD_MODEL = {
    "id": "bechtold_lodgepole_dbh_only",
    "citation": "Bechtold (2004), Table 3, Equation 3",
    "url": "https://research.fs.usda.gov/download/treesearch/7732.pdf",
    "coefficient_units": "LCW in ft; DBH in inches",
    "coefficients": [-1.1994, 1.5154, -0.0232],
    "dbh_range_in": [5.0, 62.2],
    "sample_n": 2761,
    "fit_r2": 0.54,
    "fit_rmse_ft": 2.9,
    "fit_cv_percent": 30,
    "output_scope": "Mean widest and perpendicular horizontal crown diameters of stand-grown trees",
    "evidence_class": "transferred",
    "local_error": "unknown",
}
PHOTO_DISPLAY = {
    "width_height_ratio": 0.28,
    "width_height_ratio_range": [0.24, 0.32],
    "live_crown_ratio_floor": 0.70,
    "default_crown_policy": "preserve_source",
    "evidence_class": "authored",
    "evidence_basis": "image_derived_nonmetric_silhouette_estimates",
    "uncertainty": "unknown",
    "scale_m": None,
    "camera_pose": None,
    "limitations": "Occluded bases, perspective and overlapping crowns prevent metric width estimates",
    "references": [
        {"sha256": "7b9c158facb147437e1d5a3d58bddfcc214aa6caa013c66c5155c0165c77a41b", "id": 1, "visible_tip_px": [193, 202], "visible_lower_px": [191, 854], "silhouette_width_px": 183, "base_occluded": True},
        {"sha256": "2073c39c7235803a5d8680654e80ed919975d50272abd2510d62b3cff9dcf57e", "id": 2, "visible_tip_px": [829, 163], "visible_lower_px": [801, 594], "silhouette_width_px": 150, "base_occluded": True},
        {"sha256": "4047a613d4dda3e1404fcb4e96570ad96eeeeb122e2765cf1eb9314e7c446342", "id": 3, "supports": "Small retained lower branches, straight boles and layered needle sprays; perspective width unmeasured"},
        {"sha256": "7ffc9f014f9d8934966a6fa29fa061a655d200f6ca58609bff66fbeb68c57352", "id": 4, "visible_tip_px": [758, 44], "visible_lower_px": [735, 981], "silhouette_width_px": 258, "base_occluded": True},
        {"sha256": "ee982edab9a70f9b6cd85d3b2b227e1eb1623552068d8ad1e43866021c6e3210", "id": 5, "supports": "Overlapping lower foreground foliage; individual full crown boundaries unresolved"},
    ],
}


def bechtold_crown_radius_m(dbh_m):
    """Return the transferred crown radius within the source DBH range, or unavailable."""
    if isinstance(dbh_m, bool) or not isinstance(dbh_m, (float, int)) or not math.isfinite(dbh_m) or dbh_m <= 0:
        raise ValueError("DBH requires a finite positive number in meters")
    diameter_in = dbh_m / 0.0254
    lower, upper = BECHTOLD_MODEL["dbh_range_in"]
    if diameter_in < lower or diameter_in > upper:
        return None
    b0, b1, b2 = BECHTOLD_MODEL["coefficients"]
    width_ft = b0 + b1 * diameter_in + b2 * diameter_in**2
    if width_ft <= 0:
        raise ValueError("source equation produces nonpositive crown width")
    return width_ft * 0.3048 / 2


def display_dimensions(record, fallback):
    """Return display dimensions while retaining source crown-core and donor fields."""
    identity = str(record.get("stable_id", record.get("id", "tree")))
    scale = record.get("scale", 1.0)
    height = record.get("height_m", fallback["height_m"] * scale)
    dbh = record.get("dbh_m", fallback["dbh_m"] * height / fallback["height_m"])
    core = record.get("crown_radius_m", record.get("crown_r_m", fallback["crown_radius_m"] * height / fallback["height_m"]))
    ratio = record.get("crown_ratio", fallback["crown_ratio"])
    for key, value in [("height_m", height), ("dbh_m", dbh), ("crown_radius_m", core)]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} requires a finite positive number")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or not 0 <= ratio <= 1:
        raise ValueError("crown ratio requires a finite fraction")
    if str(record.get("kind", "pine")) == "snag":
        if ratio != 0: raise ValueError("snag crown ratio must equal zero")
        return dict(height_m=height, dbh_m=dbh, crown_radius_m=core, crown_ratio=0.0,
                    source_core_radius_m=core, source_crown_ratio=ratio, envelope_class="authored_snag")
    if ratio <= 0: raise ValueError("live pine crown ratio must be positive")
    predicted = bechtold_crown_radius_m(dbh) if "dbh_m" in record else None
    fraction = int(hashlib.sha256((identity+":display_envelope").encode()).hexdigest()[:8],16) / 4294967295
    low, high = PHOTO_DISPLAY["width_height_ratio_range"]
    photo_ratio = low + (high-low)*fraction
    envelope = predicted if predicted is not None else height * photo_ratio / 2
    policy = record.get("display_crown_policy", PHOTO_DISPLAY["default_crown_policy"])
    if policy not in ("preserve_source", "photo_floor"):
        raise ValueError("Unknown display crown policy")
    display_ratio = max(ratio, PHOTO_DISPLAY["live_crown_ratio_floor"]) if policy == "photo_floor" else ratio
    return dict(height_m=height, dbh_m=dbh, crown_radius_m=max(core, envelope),
                crown_ratio=display_ratio, crown_ratio_policy=policy,
                source_core_radius_m=core, source_crown_ratio=ratio,
                envelope_class="transferred_bechtold_dbh" if predicted is not None else PHOTO_DISPLAY["evidence_class"],
                envelope_prediction_m=envelope, image_width_height_ratio=photo_ratio,
                dbh_domain_status="within_bechtold_sample_range" if predicted is not None else "bechtold_unavailable_or_outside_range",
                crown_base_class="authored_photo_floor" if policy == "photo_floor" else "retained_source_crown_ratio", local_error="unknown")
