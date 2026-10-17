#!/usr/bin/env python3
"""Offline authoring compiler for the midway world.
Reads saved geodata and writes a static world plus a reviewable placement list."""
from pathlib import Path
import argparse,json,hashlib,math
import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d, map_coordinates
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw
from shapely.geometry import LineString,Polygon,box,Point
from shapely.ops import unary_union
import rasterio

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'references'; DATA=ROOT/'data'; TEX=ROOT/'assets/textures'
E0,N0,H0=512952.5950985841,4930199.044097667,2200.
GRID,STEP,HALF=1025,4.,2048.
LIMIT=box(-HALF,-HALF,HALF,HALF)
# Junction tolerance matches WATER_JUNCTION_TOLERANCE_M in bake_world.gd.
JUNCTION_TOLERANCE_M=1.5
def load(name):return json.loads((REF/name).read_text())['features']
def local(coords):return [(p[0]-E0,N0-p[1]) for p in coords]
def parts(g):
    if g.is_empty:return []
    if g.geom_type in ('LineString','Polygon'):return [g]
    return list(g.geoms)
def densify(line,step=2.):
    count=max(1,math.ceil(line.length/step))
    return np.array([line.interpolate(float(d)).coords[0] for d in np.linspace(0,line.length,count+1)])
def sample(h,xy):
    xy=np.asarray(xy);return map_coordinates(h,[(xy[:,1]+HALF)/STEP,(xy[:,0]+HALF)/STEP],order=1,mode='nearest')
def raster_poly(polys,size=1025):
    im=Image.new('L',(size,size),0);dr=ImageDraw.Draw(im)
    for p in polys:
        def cv(coords):return [((x+HALF)/4096*(size-1),(z+HALF)/4096*(size-1)) for x,z in coords]
        dr.polygon(cv(p.exterior.coords),fill=255)
        for hole in p.interiors:dr.polygon(cv(hole.coords),fill=0)
    return np.array(im)/255.
def distance_field(points,xx,zz):
    if not len(points):return np.full_like(xx,9999.),None
    tree=cKDTree(points);d,idx=tree.query(np.stack((xx.ravel(),zz.ravel()),axis=1))
    return d.reshape(xx.shape),idx.reshape(xx.shape)

def carve_water_support(height,rivers,support_m=6.):
    """Keep the complete 4 m terrain triangles beneath narrow visible channels."""
    original=height.copy();result=height.copy();protection=np.zeros_like(height)
    target=result.ravel();base=original.ravel();protect=protection.ravel()
    for river in rivers:
        points=np.asarray(river['points']);half_width=river['width']*.5
        depth=river.get('depth_m',1.1);blend=river.get('bank_blend_m',4.)
        core=half_width+support_m;radius=core+blend
        # A symmetric node stencil includes all grid vertices within the support.
        grid=(points[:,[0,2]]+HALF)/STEP;nearest=np.rint(grid).astype(int)
        reach=math.ceil(radius/STEP)+1
        for dz in range(-reach,reach+1):
            for dx in range(-reach,reach+1):
                ix=nearest[:,0]+dx;iz=nearest[:,1]+dz
                valid=(ix>=0)&(ix<GRID)&(iz>=0)&(iz<GRID)
                distance=np.hypot((ix-grid[:,0])*STEP,(iz-grid[:,1])*STEP)
                valid&=distance<radius
                if not np.any(valid):continue
                indices=iz[valid]*GRID+ix[valid];d=distance[valid]
                weight=np.clip((radius-d)/blend,0.,1.)
                bed=points[valid,1]-depth*np.clip(1.-d/half_width,0.,1.)-.12
                candidate=base[indices]*(1.-weight)+bed*weight
                np.minimum.at(target,indices,candidate)
                np.maximum.at(protect,indices,weight)
    return result,protection

def decreasing_fit(values):
    """Least-squares non-increasing profile using pooled adjacent violators."""
    means=[];counts=[]
    for value in values:
        means.append(float(value));counts.append(1)
        while len(means)>1 and means[-2]<means[-1]:
            count=counts[-2]+counts[-1]
            value=(means[-2]*counts[-2]+means[-1]*counts[-1])/count
            means[-2:]=[value];counts[-2:]=[count]
    return np.repeat(np.asarray(means),counts)

def endpoint_clusters(arrays,tolerance=.75):
    """Cluster shared endpoints."""
    ends=np.asarray([a[j,[0,2]] for a in arrays for j in (0,-1)])
    parents=list(range(len(ends)))
    def find(i):
        while parents[i]!=i:
            parents[i]=parents[parents[i]];i=parents[i]
        return i
    for a,b in sorted(cKDTree(ends).query_pairs(tolerance)):
        ra,rb=find(a),find(b)
        if ra!=rb:parents[rb]=ra
    groups={}
    for i in range(len(ends)):groups.setdefault(find(i),[]).append(i)
    groups=list(groups.values());node_of={}
    for ni,group in enumerate(groups):
        for i in group:node_of[i]=ni
    return groups,node_of,ends

def join_water_profiles(rivers,source):
    """Fit connected Firehole reaches, then pin tributary outlets."""
    arrays=[np.asarray(r['points'],dtype=float) for r in rivers]
    groups,node_of,ends=endpoint_clusters(arrays,.75)
    node_xy={i:ends[g].mean(0) for i,g in enumerate(groups)}
    node_y={i:float(sample(source,[xy])[0]-.35) for i,xy in node_xy.items()}
    starts={i:node_of[2*i] for i in range(len(arrays))}
    stops={i:node_of[2*i+1] for i in range(len(arrays))}
    for i,a in enumerate(arrays):
        a[0,[0,2]]=node_xy[starts[i]];a[-1,[0,2]]=node_xy[stops[i]]
    main=[i for i,r in enumerate(rivers) if r['name']=='FIREHOLE RIVER']
    main_starts={starts[i]:i for i in main};main_stops={stops[i] for i in main}
    visited=set();fixed=set();minimum_grade=.00001
    # Each clipped component is independently continuous.
    seeds=[i for i in main if starts[i] not in main_stops]+main
    for seed in seeds:
        if seed in visited:continue
        chain=[];i=seed
        while i not in visited:
            visited.add(i);chain.append(i)
            nxt=main_starts.get(stops[i])
            if nxt is None:break
            i=nxt
        xy=[];slices={};offset=0
        for j,i in enumerate(chain):
            a=arrays[i];slices[i]=(offset,offset+len(a))
            xy.extend(a[:,[0,2]].tolist() if j==0 else a[1:,[0,2]].tolist())
            offset+=len(a)-1
        xy=np.asarray(xy);s=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
        raw=gaussian_filter1d(sample(source,xy),4.)-.35
        profile=decreasing_fit(raw+minimum_grade*s)-minimum_grade*s
        for i in chain:
            lo,hi=slices[i];arrays[i][:,1]=profile[lo:hi]
            node_y[starts[i]]=float(arrays[i][0,1]);node_y[stops[i]]=float(arrays[i][-1,1])
            fixed.update((starts[i],stops[i]))
    # Orient tributary trees toward a mainstem confluence or their lowest boundary outlet.
    adjacency={}
    for i in range(len(arrays)):
        if i in main:continue
        a,b=starts[i],stops[i]
        adjacency.setdefault(a,[]).append((b,i));adjacency.setdefault(b,[]).append((a,i))
    seen=set()
    for seed in sorted(adjacency):
        if seed in seen:continue
        todo=[seed];component=set()
        while todo:
            n=todo.pop()
            if n in component:continue
            component.add(n);todo.extend(v for v,_ in adjacency[n])
        seen.update(component);outlets=component.intersection(fixed)
        outlet=min(outlets or component,key=lambda n:node_y[n])
        queue=[outlet];parent={outlet:None};edge_to={}
        for n in queue:
            for neighbour,ri in adjacency[n]:
                if neighbour in parent:continue
                parent[neighbour]=n;edge_to[neighbour]=ri;queue.append(neighbour)
        for n in queue[1:]:
            downstream=parent[n];ri=edge_to[n];a=arrays[ri]
            if starts[ri]!=n:a=a[::-1].copy();arrays[ri]=a
            starts[ri],stops[ri]=n,downstream
            xy=a[:,[0,2]];s=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
            length=max(float(s[-1]),.001)
            if n not in fixed:node_y[n]=max(node_y[n],node_y[downstream]+minimum_grade*length)
            high,low=node_y[n],node_y[downstream]
            grade=min(minimum_grade,max(0.,(high-low)/length))
            raw=gaussian_filter1d(sample(source,xy),4.)-.35;t=s/length
            raw+=(high-raw[0])*(1-t)+(low-raw[-1])*t
            constrained=np.clip(raw+grade*s,low+grade*length,high)
            constrained[0]=high;constrained[-1]=low+grade*length
            a[:,1]=decreasing_fit(constrained)-grade*s
            a[0,1]=high;a[-1,1]=low
    trees=[cKDTree(a[:,[0,2]]) for a in arrays]
    for i,r in enumerate(rivers):
        r['points']=arrays[i].round(4).tolist()
        r['endpoint_node_ids']=[f'water_node_{starts[i]:03}',f'water_node_{stops[i]:03}']
        classes=[]
        for e in arrays[i][[0,-1]][:,[0,2]]:
            gap=min((t.query(e)[0] for k,t in enumerate(trees) if k!=i),default=math.inf)
            if gap<=JUNCTION_TOLERANCE_M:classes.append('joined')
            elif max(abs(e[0]),abs(e[1]))>=HALF-.5:classes.append('domain_exit')
            else:classes.append('open')
        r['profile_status']=(f'DEM-constrained illustrative stage; downstream-monotone; '
                             f'upstream {classes[0]}; downstream {classes[1]}')
    return [dict(id=f'water_node_{i:03}',position=[round(node_xy[i][0],4),round(node_y[i],4),round(node_xy[i][1],4)]) for i in sorted(node_xy)]

def join_route_profiles(routes):
    """Make intersecting route endpoints one level."""
    arrays=[np.asarray(r['points'],dtype=float) for r in routes]
    groups,node_of,ends=endpoint_clusters(arrays,.75);targets={}
    for ni,group in enumerate(groups):
        if len(group)<2:continue
        xy=ends[group].mean(0)
        y=float(np.median([arrays[e//2][0 if e%2==0 else -1,1] for e in group]))
        for e in group:targets[e]=np.array([xy[0],y,xy[1]])
    for i,a in enumerate(arrays):
        s=np.r_[0,np.cumsum(np.linalg.norm(np.diff(a[:,[0,2]],axis=0),axis=1))]
        length=max(float(s[-1]),.001);ramp=min(length,max(8.,routes[i]['width']*3))
        start_delta=targets.get(2*i,a[0])-a[0];end_delta=targets.get(2*i+1,a[-1])-a[-1]
        ws=np.clip(1-s/ramp,0,1);we=np.clip(1-(length-s)/ramp,0,1)
        ws=ws*ws*(3-2*ws);we=we*we*(3-2*we)
        a+=ws[:,None]*start_delta+we[:,None]*end_delta
        routes[i]['points']=a.round(4).tolist()
    return len({node_of[e] for e in targets})

def grade_bridge_approaches(routes,minimum_run_m=12.,maximum_angle_deg=18.):
    """Extend bridge grades onto dry approaches."""
    limit=math.tan(math.radians(maximum_angle_deg));total=0;max_angle=0.
    for route in routes:
        spans=route.get('bridge_spans',[])
        if not spans:continue
        points=np.asarray(route['points'],dtype=float);baseline=points[:,1].copy()
        s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points[:,[0,2]],axis=0),axis=1))]
        fixed=np.zeros(len(points),dtype=bool)
        for lo,hi in spans:fixed[lo:hi+1]=True
        def fit(lo,hi):
            length=float(s[hi]-s[lo]);secant=(baseline[hi]-baseline[lo])/max(length,.0001)
            m0=(baseline[lo]-baseline[lo-1])/max(s[lo]-s[lo-1],.0001) if lo>0 else secant
            m1=(baseline[hi+1]-baseline[hi])/max(s[hi+1]-s[hi],.0001) if hi+1<len(points) else secant
            if abs(secant)<1e-9:m0=m1=0.
            else:
                sign=1. if secant>0 else -1.;bound=min(limit,3.*abs(secant))
                m0=sign*float(np.clip(sign*m0,0.,bound));m1=sign*float(np.clip(sign*m1,0.,bound))
                norm=math.hypot(m0/secant,m1/secant)
                if norm>3.:m0*=3./norm;m1*=3./norm
            u=(s[lo:hi+1]-s[lo])/max(length,.0001)
            values=(2*u**3-3*u**2+1)*baseline[lo]+(u**3-2*u**2+u)*length*m0
            values+=(-2*u**3+3*u**2)*baseline[hi]+(u**3-u**2)*length*m1
            values[0]=baseline[lo];values[-1]=baseline[hi]
            worst=float(np.max(np.abs(np.diff(values))/np.maximum(np.diff(s[lo:hi+1]),.0001)))
            return values,worst
        intervals=[];indices=np.where(~fixed)[0]
        for gap in np.split(indices,np.where(np.diff(indices)>1)[0]+1):
            if not len(gap):continue
            first,last=int(gap[0]),int(gap[-1]);left=first-1 if first>0 else None;right=last+1 if last+1<len(points) else None
            proposals=[]
            if left is not None:
                far=right if right is not None else len(points)-1
                hi=min(far,int(np.searchsorted(s,s[left]+minimum_run_m)))
                while hi<far and fit(left,hi)[1]>limit:hi+=1
                proposals.append([left,hi])
            if right is not None:
                far=left if left is not None else 0
                lo=max(far,int(np.searchsorted(s,s[right]-minimum_run_m,side='right'))-1)
                while lo>far and fit(lo,right)[1]>limit:lo-=1
                proposals.append([lo,right])
            if len(proposals)==2 and proposals[0][1]>=proposals[1][0]:proposals=[[left,right]]
            intervals.extend(proposals)
        for lo,hi in intervals:
            if hi<=lo:continue
            values,worst=fit(lo,hi)
            if worst>limit+1e-6:raise ValueError(f'{route["id"]}: bridge approach {lo}:{hi} needs a longer authored grade')
            points[lo:hi+1,1]=values
            total+=1;max_angle=max(max_angle,math.degrees(math.atan(worst)))
        # Preserve shared endpoint levels and bridge vertices.
        points[fixed,1]=baseline[fixed];points[[0,-1],1]=baseline[[0,-1]]
        route['points']=points.round(4).tolist()
        route['bridge_approach_spans']=intervals
        route['bridge_approach_profile_status']='Endpoint-pinned cubic grade; at least 12 m where route length permits; maximum 18 degrees'
    return dict(count=total,maximum_slope_degrees=round(max_angle,4))

def trim_approach_terrain(height,routes,clearance_m=.06):
    """Remove coarse-grid protrusions through the actual ramp triangles."""
    samples=[]
    for route in routes:
        intervals=route.get('bridge_approach_spans',[])
        if not intervals:continue
        p=np.asarray(route['points']);tangent=np.vstack((p[1]-p[0],p[2:]-p[:-2],p[-1]-p[-2]))
        side=np.column_stack((-tangent[:,2],np.zeros(len(p)),tangent[:,0]));side/=np.linalg.norm(side,axis=1)[:,None]
        left=p-side*route['width']*.5;right=p+side*route['width']*.5
        for lo,hi in intervals:
            for i in range(lo,hi):
                for tri in [np.asarray([left[i],left[i+1],right[i]]),np.asarray([right[i],left[i+1],right[i+1]])]:
                    count=max(2,math.ceil(max(np.linalg.norm(tri[a]-tri[b]) for a,b in [(0,1),(1,2),(2,0)])/.5))
                    uv=np.asarray([(u/count,v/count) for u in range(count+1) for v in range(count+1-u)])
                    samples.append(tri[0]+uv[:,0,None]*(tri[1]-tri[0])+uv[:,1,None]*(tri[2]-tri[0]))
    if not samples:return 0.
    q=np.concatenate(samples);q=q[np.max(np.abs(q[:,[0,2]]),axis=1)<=HALF]
    g=np.clip((q[:,[0,2]]+HALF)/STEP,0.,GRID-1-1e-5);ij=np.floor(g).astype(int);f=g-ij
    a=ij[:,1]*GRID+ij[:,0];b=a+1;c=a+GRID;d=c+1;fx=f[:,0];fz=f[:,1];first=fx+fz<=1
    original=height.ravel().copy();flat=height.ravel()
    ground=np.where(first,original[a]+fx*(original[b]-original[a])+fz*(original[c]-original[a]),original[d]+(1-fx)*(original[c]-original[d])+(1-fz)*(original[b]-original[d]))
    excess=np.maximum(ground-q[:,1]+clearance_m,0.);active=excess>0
    for indices in [np.where(first,a,b),np.where(first,b,d),c]:
        np.minimum.at(flat,indices[active],original[indices[active]]-excess[active])
    return round(float(excess.max()),4)

def add_excelsior_outflow(rivers,source):
    """An explicitly authored representative outlet, tied to pool and river levels."""
    trace=json.loads((REF/'excelsior_outflow_trace.json').read_text())
    xy=np.asarray(trace['polyline_local_xz_m'],dtype=float)
    parent=None;nearest=None;best=float('inf')
    for r in rivers:
        if r['name']!='FIREHOLE RIVER':continue
        a=np.asarray(r['points']);ds=np.linalg.norm(a[:,[0,2]]-xy[-1],axis=1);i=int(np.argmin(ds))
        if ds[i]<best:best=float(ds[i]);parent=r;nearest=(i,a[i])
    if parent is None:raise ValueError('Excelsior outflow needs the mapped Firehole River')
    xy[-1]=nearest[1][[0,2]];xy=densify(LineString(xy),1.)
    f=next(f for f in load('yell_hydro_lakes_utm12.json') if f['attributes']['OBJECTID']==1030)
    ring=np.asarray(local(f['geometry']['rings'][0]))
    pool_y=float(np.percentile(sample(source,ring),30))-.22;river_y=float(nearest[1][1])
    if pool_y<=river_y:raise ValueError('Excelsior outlet must descend to the Firehole')
    s=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
    profile=np.clip(sample(source,xy)-.08,river_y,pool_y)
    profile[0]=pool_y;profile[-1]=river_y;profile=decreasing_fit(profile)
    profile[0]=pool_y;profile[-1]=river_y
    rivers.append(dict(id='authored_excelsior_outflow_01',name='Excelsior thermal outflow',width=2.4,
  depth_m=.15,bank_blend_m=3.,points=np.column_stack((xy[:,0],profile,xy[:,1])).round(4).tolist(),
  flow_mps=.7,temperature_c=82.,flow_m3_s=.252,thermal=True,
  discharge_status='Illustrative aggregate based on the NPS lower bound of 4,000 US gal/min; not calibrated for this individual branch',
  source_status='Hand traced representative 2022 NAIP drainage; pool/river joins are constrained',
  source_trace='references/excelsior_outflow_trace.json',
  source_pool_id='pool_1030_0',target_river_id=parent['id'],target_vertex_index=nearest[0],
  profile_status='Bounded by Excelsior pool and Firehole stage; downstream-monotone'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--placements-replace',action='store_true');args=parser.parse_args()
    with rasterio.open(REF/'dem.tif') as ds:
        source=ds.read(1).astype(np.float64)-H0
    assert source.shape==(GRID,GRID) and np.isfinite(source).all()
    h=source.copy();gx=np.linspace(-HALF,HALF,GRID);xx,zz=np.meshgrid(gx,gx)
    routes=[];all_points=[]
    for kind,filename in [('road','yell_roads_utm12.json'),('trail','yell_trails_utm12.json')]:
        for f in load(filename):
            a=f['attributes'];name=a.get('RDNAME' if kind=='road' else 'TRLNAME') or 'Access road'
            if 'Fountain Freight' in name:continue # Aligned with Fairy Falls Trail
            if kind=='trail' and ('Powerline' in name or 'Spur' in name):continue
            for path in f['geometry']['paths']:
                for j,ln in enumerate(parts(LineString(local(path)).intersection(LIMIT))):
                    if ln.geom_type!='LineString' or ln.length<1:continue
                    xy=densify(ln,2.)
                    surface=a.get('RDSURFACE' if kind=='road' else 'TRLSURFACE','Native')
                    width=7.2 if name=='Grand Loop Road' else (4.8 if kind=='road' else (2.1 if surface=='Wood' else 2.3))
                    # Plank thickness and bridge elevations are art/engineering values.
                    routes.append(dict(id=f'{kind}_{a["OBJECTID"]}_{j}',name=name,kind=kind,surface=surface,width=width,xy=xy,source_id=a['OBJECTID'],accuracy=a.get('XYACCURACY','Unknown')))
                    all_points.extend(xy)
    route_dist,_=distance_field(np.array(all_points),xx,zz)
    # Authored widths are not surveyed banks.
    rivers=[]
    for f in load('yell_hydro_rivers_utm12.json'):
        a=f['attributes'];name=a['STREAMNAME']
        if name not in ['FIREHOLE RIVER','RABBIT CREEK','FAIRY CREEK','WHITE CREEK','MALLARD CREEK']:continue
        for path in f['geometry']['paths']:
            for j,ln in enumerate(parts(LineString(local(path)).intersection(LIMIT))):
                if ln.geom_type!='LineString' or ln.length<3:continue
                xy=densify(ln,3.)
                if name=='FIREHOLE RIVER' and xy[0,1]<xy[-1,1]:xy=xy[::-1]
                sy=gaussian_filter1d(sample(source,xy),4.)-0.35
                width=22. if name=='FIREHOLE RIVER' else 3.5
                rivers.append(dict(id=f'river_{a["OBJECTID"]}_{j}',name=name,width=width,points=np.column_stack((xy[:,0],sy,xy[:,1])).round(4).tolist(),flow_mps=.58 if width>5 else .35))
    water_junctions=join_water_profiles(rivers,source)
    add_excelsior_outflow(rivers,source)
    river_pts=[];river_surfaces=[];river_widths=[];river_depths=[];river_blends=[]
    for river in rivers:
        points=np.asarray(river['points']);river_pts.extend(points[:,[0,2]])
        river_surfaces.extend(points[:,1]);river_widths.extend([river['width']]*len(points))
        river_depths.extend([river.get('depth_m',1.1)]*len(points))
        river_blends.extend([river.get('bank_blend_m',4.)]*len(points))
    rd,ri=distance_field(np.array(river_pts),xx,zz)
    surf=np.array(river_surfaces)[ri];rw=np.array(river_widths)[ri]*.5
    depth=np.asarray(river_depths)[ri];blend=np.asarray(river_blends)[ri]
    h,river_support=carve_water_support(h,rivers)
    # Lakes use official polygons.
    pools=[];all_water=[]
    names={1034:'Grand Prismatic Spring',1030:'Excelsior Geyser Crater',1028:'Turquoise Pool',1029:'Opal Pool'}
    for f in load('yell_hydro_lakes_utm12.json'):
        a=f['attributes'];pid=a['OBJECTID']
        if not f['geometry']['rings']:continue
        poly=Polygon(local(f['geometry']['rings'][0])).buffer(0).intersection(LIMIT)
        for j,p in enumerate(parts(poly)):
            if p.geom_type!='Polygon' or p.area<8:continue
            center=np.array(p.centroid.coords[0]); ring=np.array(p.exterior.coords)[:-1]
            # DEMs do not measure bathymetry. Carve modest invisible bathymetry for visual integration.
            sy=float(np.percentile(sample(source,ring),30))-.22
            mask=raster_poly([p]);from scipy.ndimage import distance_transform_edt
            inside=distance_transform_edt(mask)*STEP
            floor=sy-0.45-np.minimum(inside*.25,7.)
            h=np.where(mask>.5,np.minimum(h,floor),h)
            thermal=pid in names
            pools.append(dict(id=f'pool_{pid}_{j}',source_id=pid,name=names.get(pid,a.get('LAKENAME') or 'Forest pond'),thermal=thermal,center=[round(center[0],4),round(sy,4),round(center[1],4)],ring=[[round(x,4),round(z,4)] for x,z in ring],area_m2=round(p.area,1),temperature_c=(72. if pid==1034 else (82. if pid==1030 else 63.)) if thermal else 16.,temperature_status='Illustrative scenario parameter; not a source measurement'))
            all_water.append(p)
    # Grade roads to source cross-section center heights with a two-meter verge blend.
    for r in routes:
        xy=r.pop('xy');ys=sample(h,xy)
        if r['kind']=='road':ys=gaussian_filter1d(ys,3.)
        elif r['surface']!='Wood':ys=gaussian_filter1d(ys,1.)
        # Bridge detected when path spans a mapped stream.
        dcenter,_=cKDTree(np.array(river_pts)).query(xy)
        bridge_mask=dcenter<13.
        if np.any(bridge_mask) and not np.all(bridge_mask):
            inds=np.where(bridge_mask)[0]
            for sub in np.split(inds,np.where(np.diff(inds)>1)[0]+1):
                lo=max(0,int(sub[0])-8);hi=min(len(xy)-1,int(sub[-1])+8)
                if hi>lo:
                    r.setdefault('bridge_spans',[]).append([lo,hi])
                    ends=sample(source,xy[[lo,hi]])+0.6
                    ys[lo:hi+1]=np.linspace(ends[0],ends[1],hi-lo+1)
            r['has_bridge']=True
        if r['kind']=='road':
            d,ix=distance_field(xy,xx,zz); target=ys[ix];w=r['width']*.5
            weight=np.clip((w+3-d)/3,0,1)
            weight=np.where(rd<14,0,weight)*(1-river_support) # Preserve channel support vertices
            h=h*(1-weight)+target*weight
        ys+=.28 if r['surface']=='Wood' else .12
        r['points']=np.column_stack((xy[:,0],ys,xy[:,1])).round(4).tolist()
    route_junction_count=join_route_profiles(routes)
    bridge_approach_report=grade_bridge_approaches(routes)
    # Re-grade corrected road approaches after snapping endpoint levels. Stream exclusions preserved.
    for r in routes:
        if r['kind']!='road':continue
        points=np.asarray(r['points']);xy=points[:,[0,2]];ys=points[:,1]-.12
        d,ix=distance_field(xy,xx,zz);target=ys[ix];w=r['width']*.5
        weight=np.clip((w+3-d)/3,0,1);weight=np.where(rd<14,0,weight)*(1-river_support)
        h=h*(1-weight)+target*weight
    # Native/asphalt trail approaches receive local verge grading.
    for route in routes:
        if route['kind']=='road' or route['surface']=='Wood':continue
        points=np.asarray(route['points']);half_width=route['width']*.5;blend=3.
        for lo,hi in route.get('bridge_approach_spans',[]):
            xy=points[lo:hi+1][:,[0,2]];ys=points[lo:hi+1,1]-.12
            mn=np.floor((xy.min(0)-half_width-blend+HALF)/STEP).astype(int)
            mx=np.ceil((xy.max(0)+half_width+blend+HALF)/STEP).astype(int)
            x0,z0=np.clip(mn,0,GRID-1);x1,z1=np.clip(mx,0,GRID-1)
            region=np.s_[z0:z1+1,x0:x1+1]
            d,ix=distance_field(xy,xx[region],zz[region]);target=ys[ix]
            weight=np.clip((half_width+blend-d)/blend,0,1)
            weight=np.where(rd[region]<14,0,weight)*(1-river_support[region])
            h[region]=h[region]*(1-weight)+target*weight
    bridge_approach_report['maximum_downward_terrain_trim_m']=trim_approach_terrain(h,routes)
    # Record the authored revision.
    (DATA/'terrain.f32').write_bytes(h.astype('<f4').tobytes())
    orth=np.asarray(Image.open(REF/'orthophoto.jpg').resize((GRID,GRID),Image.Resampling.BILINEAR)).astype(float)/255
    light=orth.mean(2)
    # Painted habitat support derived from photographed cover, overridden by explicit constraints.
    mineral=np.clip((light-.44)*5,0,1)
    green=np.clip((orth[:,:,1]-orth[:,:,0]+.045)*8,0,1)
    meadow=np.clip((light-.14)*2.3,0,1)*(1-mineral)
    wet=np.clip(1-rd/65,0,1)
    mask=np.stack((mineral,meadow,wet),2)
    Image.fromarray((np.clip(mask,0,1)*255).astype('uint8')).save(TEX/'habitat_mask.png')
    Image.open(REF/'orthophoto.jpg').save(TEX/'midway_macro.jpg',quality=93)
    # Material noise is surface microdetail only.
    rng=np.random.default_rng(1209)
    noise=gaussian_filter(rng.random((256,256)),3,mode='wrap');noise=(noise-noise.min())/(noise.max()-noise.min())
    Image.fromarray((noise*255).astype('uint8')).save(TEX/'detail.png')
    n2=gaussian_filter(rng.random((512,512)),2,mode='wrap');dy,dx=np.gradient(n2)
    n=np.stack((-dx*13,np.ones_like(dx),-dy*13),2);n/=np.linalg.norm(n,axis=2,keepdims=True)
    # Tangent normal map: x/right, y/up, z/normal.
    normal=np.stack((n[:,:,0],n[:,:,2],n[:,:,1]),2)*.5+.5
    Image.fromarray((normal*255).astype('uint8')).save(TEX/'water_normal.png')
    # Cropped thermal apron photo uses real mineral drainage colors.
    Image.open(REF/'orthophoto.jpg').save(TEX/'thermal_reference.jpg',quality=95)
    # Explicit scene anchors, source-aligned where named.
    overview=np.array([[-252.,159.]])
    anchors=[dict(id='overlook',title='Grand Prismatic Overlook',xz=[-252.,159.],look=[-99.,-9.],note='NPS overlook deck spur endpoint'),dict(id='boardwalk',title='Midway boardwalk',xz=[-155.,-100.],look=[-99.,-9.],note='Closest boardwalk point to the western pools'),dict(id='river',title='Firehole bridge',xz=[70.,-261.],look=[45.,-140.],note='Bridge approach; snapped to trail geometry'),dict(id='trailhead',title='Fairy Falls approach',xz=[260.,950.],look=[-120.,350.],note='Start point snapped to Fairy Falls alignment')]
    midpaths=np.concatenate([np.array(r['points']) for r in routes if r['kind']=='trail' and ('Midway' in r['name'] or 'Fairy Falls' in r['name'])])
    for a in anchors:
        xz=np.array(a.pop('xz'))
        if a['id']!='overlook':
            candidate=midpaths
            if a['id']=='trailhead':candidate=np.concatenate([np.array(r['points']) for r in routes if 'Fairy Falls' in r['name']])
            d=np.linalg.norm(candidate[:,[0,2]]-xz,axis=1);point=candidate[np.argmin(d)]
            a['position']=[float(point[0]),float(point[1]+.15),float(point[2])]
        else:a['position']=[float(xz[0]),float(sample(h,[xz])[0]+.48),float(xz[1])]
        look=a.pop('look');a['target']=[look[0],float(sample(h,[look])[0])+1.4,look[1]]
    world=dict(version=1,title='Yellowstone / Midway',georeference=dict(crs='EPSG:32612',origin=[E0,N0,H0],vertical_datum='NAVD88',unit='metre',extent=4096,grid_size=1025,grid_step_m=4),routes=routes,rivers=rivers,water_junctions=water_junctions,pools=pools,anchors=anchors)
    (DATA/'world.json').write_text(json.dumps(world,indent=2))
    # Offline proposals from measured cover; editing uses placement_overrides.json.
    path=DATA/'placements.json'
    if not path.exists() or args.placements_replace:
        trees=[];grass=[];rocks=[];logs=[];rand=np.random.default_rng(553177)
        water_union=unary_union(all_water)
        route_tree=cKDTree(np.array(all_points));river_tree=cKDTree(np.array(river_pts))
        def image_at(x,z):
            ix=int(np.clip((x+HALF)/4,0,1024));iz=int(np.clip((z+HALF)/4,0,1024));return orth[iz,ix],mineral[iz,ix],h[iz,ix]
        # Jittered candidate cells are a drafting aid. Accepted transforms persisted with stable IDs.
        for iz,z in enumerate(np.arange(-2028,2030,15.)):
            for ix,x in enumerate(np.arange(-2028,2030,15.)):
                x=x+rand.uniform(-5,5);z0=z+rand.uniform(-5,5)
                rgb,m,y=image_at(x,z0)
                road_d=float(route_tree.query([x,z0])[0]);water_d=float(river_tree.query([x,z0])[0])
                forest=(rgb.mean()<.32 and rgb[1]>rgb[0]*.96 and m<.1)
                if forest and road_d>8 and water_d>20 and not water_union.buffer(5).contains(Point(x,z0)):
                    height=rand.uniform(8,18);variant=int(rand.integers(0,3))
                    trees.append(dict(id=f'pine_{iz:03}_{ix:03}',kind='pine',position=[round(x,3),round(float(sample(h,[[x,z0]])[0])-.15,3),round(z0,3)],yaw=round(float(rand.uniform(0,math.tau)),3),scale=round(height/15,3),variant=variant))
        # Walkable corridors receive groundcover; thermal crust stays bare.
        candidates=[]
        for r in routes:
            if r['kind']!='trail':continue
            for p in r['points'][::3]:
                for k in range(6):
                    x=p[0]+rand.uniform(-22,22);z=p[2]+rand.uniform(-22,22)
                    rgb,m,y=image_at(x,z)
                    if abs(x)>2035 or abs(z)>2035:continue
                    if m>.12 or route_tree.query([x,z])[0]<r['width']/2+.6 or river_tree.query([x,z])[0]<15:continue
                    if water_union.buffer(2).contains(Point(x,z)):continue
                    grass.append(dict(id=f'grass_{len(grass):05}',kind='grass',position=[round(x,3),round(float(sample(h,[[x,z]])[0]),3),round(z,3)],yaw=round(float(rand.uniform(0,math.tau)),3),scale=round(float(rand.uniform(.45,1.2)),3),variant=len(grass)%4))
        for t in trees[::71]:
            p=t['position'];logs.append(dict(id=f'log_{len(logs):03}',kind='log',position=p,yaw=t['yaw'],scale=t['scale']))
        for t in trees[::43]:
            p=t['position'];rocks.append(dict(id=f'rock_{len(rocks):03}',kind='rock',position=p,yaw=t['yaw'],scale=round(t['scale']*.6,3)))
        path.write_text(json.dumps(dict(schema=1,status='fixed authoring draft; review individual placements against the aerial, then edit normally',trees=trees,grass=grass,rocks=rocks,logs=logs),separators=(',',':')))
        print('Fixed placement draft:',len(trees),'trees',len(grass),'tufts',len(rocks),'rocks',len(logs),'deadwood')
    (DATA/'placement_overrides.json').touch(exist_ok=True)
    if not (DATA/'placement_overrides.json').read_text().strip():(DATA/'placement_overrides.json').write_text('{"schema":1,"remove":[],"replace":{},"add":[]}\n')
    report={'source_unchanged_sha256':hashlib.sha256((REF/'terrain_source.f32').read_bytes()).hexdigest(),'height_range_local_m':[float(h.min()),float(h.max())],'max_authoring_cut_m':float((h-source).min()),'route_count':len(routes),'route_junction_count':route_junction_count,'water_junction_count':len(water_junctions),'waterbody_count':len(pools),'river_count':len(rivers),'source_samples':GRID*GRID,'channel_terrain_support_m':6.,'notes':['Widths, road elevations, underwater depth and planting positions are authored approximations.','Channel terrain support extends six metres beyond visual half-width to keep all 4 m master-grid triangles below water; these broad support banks need future local mesh refinement.','Shared route endpoints and channel confluences have common heights.','Fairy Creek and White Creek exit the south domain boundary without a Firehole confluence inside the domain; the source hydrography places the White Creek and Firehole confluence vertex 30 m south of the boundary, so the domain clip severs it.','Excelsior outflow is one representative authored branch, not a surveyed hydraulic reconstruction.','No terrain noise. No runtime random scenery.','All macro imagery is from NAIP source; exact imagery provenance retained in references.']}
    report['bridge_approaches']=bridge_approach_report
    (DATA/'bake_report.json').write_text(json.dumps(report,indent=2));print(report)

if __name__=='__main__':main()
