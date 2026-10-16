"""Optional VTK motion previews."""
from __future__ import annotations
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from .core import skin,Pose,Skeleton
from .gltf import MeshAsset


class Preview:
    def __init__(self,asset: MeshAsset,skeleton: Skeleton,joints,weights,
                 width: int=1000,height: int=660,view: str='threequarter',ground: bool=True,water: bool=False):
        try:
            import vtk
            from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray,vtk_to_numpy
        except ImportError as e:
            raise RuntimeError('Install yellowstone-wildlife-motion[preview] to render previews') from e
        self.vtk=vtk;self.to=numpy_to_vtk;self.back=vtk_to_numpy
        self.asset=asset;self.skeleton=skeleton;self.joints=joints;self.weights=weights
        self.width=width;self.height=height
        self.points=vtk.vtkPoints();self.points.SetData(numpy_to_vtk(asset.vertices.astype(np.float32),deep=True))
        self.normal_data=numpy_to_vtk(asset.normals.astype(np.float32),deep=True)
        self.ren=vtk.vtkRenderer();self.ren.SetBackground(.045,.057,.070)
        self.win=vtk.vtkRenderWindow();self.win.SetOffScreenRendering(1);self.win.SetSize(width,height)
        self.win.SetMultiSamples(4);self.win.AddRenderer(self.ren)
        for pi,(fa,fb) in enumerate(asset.primitive_face_slices):
            poly=vtk.vtkPolyData();poly.SetPoints(self.points)
            cells=vtk.vtkCellArray()
            # Modern offsets/connectivity avoids deprecated SetCells.
            f=asset.faces[fa:fb].astype(np.int64)
            cells.SetData(numpy_to_vtkIdTypeArray(np.arange(len(f)+1,dtype=np.int64)*3,deep=True),
                          numpy_to_vtkIdTypeArray(f.ravel(),deep=True));poly.SetPolys(cells)
            poly.GetPointData().SetNormals(self.normal_data)
            if asset.uvs is not None:poly.GetPointData().SetTCoords(numpy_to_vtk(asset.uvs.astype(np.float32),deep=True))
            mapper=vtk.vtkPolyDataMapper();mapper.SetInputData(poly)
            if asset.colors is not None:
                # glTF vertex colors are linear, display conversion is approximate.
                colors=np.round(255*np.clip(asset.colors,0,1)).astype(np.uint8)
                poly.GetPointData().SetScalars(numpy_to_vtk(colors,deep=True))
                mapper.SetColorModeToDirectScalars();mapper.ScalarVisibilityOn()
            else:mapper.ScalarVisibilityOff()
            actor=vtk.vtkActor();actor.SetMapper(mapper)
            tex=asset.texture(pi,1536)
            if tex is not None:
                arr=np.asarray(tex).copy();td=vtk.vtkImageData();td.SetDimensions(tex.width,tex.height,1)
                pixels=numpy_to_vtk(arr.reshape(-1,4),deep=True);pixels.SetNumberOfComponents(4);td.GetPointData().SetScalars(pixels)
                t=vtk.vtkTexture();t.SetInputData(td);t.InterpolateOn();actor.SetTexture(t)
            else:
                p=asset.doc['meshes'][asset.metadata['mesh_index']]['primitives'][pi]
                mats=asset.doc.get('materials',[])
                factor=mats[p['material']].get('pbrMetallicRoughness',{}).get('baseColorFactor',[.7,.72,.73,1]) if 'material' in p else [.7,.72,.73,1]
                actor.GetProperty().SetColor(*factor[:3])
            actor.GetProperty().SetAmbient(.50);actor.GetProperty().SetDiffuse(.55)
            actor.GetProperty().SetSpecular(.06);actor.GetProperty().SetInterpolationToPhong()
            self.ren.AddActor(actor)
        self.height_units=skeleton.metadata['height']
        h=self.height_units
        if ground:
            gridpoints=vtk.vtkPoints();lines=vtk.vtkCellArray()
            for z in np.arange(-8*h,12*h,.25*h):
                a=gridpoints.InsertNextPoint(-6*h,-.004*h,z);b=gridpoints.InsertNextPoint(6*h,-.004*h,z)
                lines.InsertNextCell(2);lines.InsertCellPoint(a);lines.InsertCellPoint(b)
            for x in np.arange(-6*h,6*h,.25*h):
                a=gridpoints.InsertNextPoint(x,-.004*h,-8*h);b=gridpoints.InsertNextPoint(x,-.004*h,12*h)
                lines.InsertNextCell(2);lines.InsertCellPoint(a);lines.InsertCellPoint(b)
            pd=vtk.vtkPolyData();pd.SetPoints(gridpoints);pd.SetLines(lines);mp=vtk.vtkPolyDataMapper();mp.SetInputData(pd)
            a=vtk.vtkActor();a.SetMapper(mp);a.GetProperty().SetColor(.19,.23,.27);a.GetProperty().SetOpacity(.35);self.ren.AddActor(a)
        if water:
            plane=vtk.vtkPlaneSource();plane.SetOrigin(-4*h,0,-4*h);plane.SetPoint1(4*h,0,-4*h);plane.SetPoint2(-4*h,0,4*h)
            mp=vtk.vtkPolyDataMapper();mp.SetInputConnection(plane.GetOutputPort())
            actor=vtk.vtkActor();actor.SetMapper(mp);actor.GetProperty().SetColor(.16,.42,.49)
            actor.GetProperty().SetOpacity(.35);actor.GetProperty().SetAmbient(.65);self.ren.AddActor(actor)
        self.center=(asset.vertices.min(0)+asset.vertices.max(0))*.5
        self.camera=self.ren.GetActiveCamera();self.camera.ParallelProjectionOn();self.camera.SetViewUp(0,1,0)
        self.view=view
        self.camera_offset=np.array([4.5,.9,1.7])*h if view=='threequarter' else np.array([5.,.08,0])*h
        if view=='top':self.camera_offset=np.array([0.,5.,0.])*h;self.camera.SetViewUp(0,0,1)
        scale=max(h*.68,np.ptp(asset.vertices[:,2])*.58*height/width)
        self.camera.SetParallelScale(scale)
        self.capture=vtk.vtkWindowToImageFilter();self.capture.SetInput(self.win);self.capture.ReadFrontBufferOff()
        try:
            self.font=ImageFont.truetype('DejaVuSans.ttf',18)
            self.small=ImageFont.truetype('DejaVuSans.ttf',12)
        except OSError:self.font=self.small=ImageFont.load_default()

    def frame(self,pose: Pose,title: str='',subtitle: str='',follow_root: bool=False) -> Image.Image:
        vertices=skin(self.asset.vertices,self.skeleton,self.joints,self.weights,pose)
        self.back(self.points.GetData())[:]=vertices
        self.points.GetData().Modified();self.points.Modified()
        normals=np.zeros_like(vertices)
        for k in range(4):
            ids=self.joints[:,k]
            normals+=self.weights[:,k,None]*np.einsum('nij,nj->ni',pose.rotations[ids],self.asset.normals)
        normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
        self.back(self.normal_data)[:]=normals;self.normal_data.Modified()
        center=self.center.copy()
        if follow_root:center+=pose.positions[0]-self.skeleton.rest[0]
        self.camera.SetFocalPoint(*center);self.camera.SetPosition(*(center+self.camera_offset))
        self.ren.ResetCameraClippingRange();self.win.Render();self.capture.Modified();self.capture.Update()
        out=self.capture.GetOutput();array=self.back(out.GetPointData().GetScalars())
        image=Image.fromarray(np.flipud(array.reshape(self.height,self.width,-1)[:,:,:3]).copy())
        d=ImageDraw.Draw(image,'RGBA');d.rounded_rectangle((16,14,self.width-16,78),radius=9,fill=(10,18,25,220))
        d.text((31,25),title,font=self.font,fill=(232,239,241));d.text((31,53),subtitle,font=self.small,fill=(167,187,198))
        return image

    def close(self):self.win.Finalize()


def render_video(asset,skeleton,joints,weights,pose_function,output: str | Path,
                 duration: float=4.,fps: int=24,title: str='',view: str='threequarter',
                 follow_root: bool=False,ground: bool=True,water: bool=False) -> None:
    import imageio.v2 as imageio
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    preview=Preview(asset,skeleton,joints,weights,view=view,ground=ground,water=water)
    try:
        with imageio.get_writer(str(output),fps=fps,codec='libx264',quality=8,
                               macro_block_size=2,ffmpeg_log_level='error',
                               ffmpeg_params=['-movflags','+faststart']) as writer:
            for i in range(round(duration*fps)):
                t=i/fps
                im=preview.frame(pose_function(t),title,f'{view}  |  t = {t:.2f} s  |  procedural controls; not species-calibrated',follow_root)
                writer.append_data(np.asarray(im))
                if i==0:im.save(output.with_suffix('.png'))
    finally:preview.close()
