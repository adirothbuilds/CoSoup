"""Build CoSoup's animated bowl in Blender. No network, data or credentials.

blender --background --python tools/mascots/build_bowl.py -- \
  --output-dir apps/web/public/mascots --scene-file /tmp/cosoup-bowl.blend
The web uses the transparent, pre-rendered loop rather than a WebGL context.
"""
import argparse
import math
import subprocess
import sys
from pathlib import Path
import bpy
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--scene-file', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
args.output_dir.mkdir(parents=True, exist_ok=True)
args.scene_file.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)

def material(name, color, roughness=.45):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*color,1)
    m.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=roughness
    return m

charcoal=material('Charcoal ceramic',(.055,.075,.077))
teal=material('Teal glaze',(.055,.35,.31),.3)
soup=material('Golden soup',(.95,.55,.10),.3)
cream=material('Cream',(.98,.9,.7))
eye=material('Warm brown',(.20,.095,.035))
shine=material('Eye sparkle',(.99,.98,.91))
root=bpy.data.objects.new('CoSoup bowl',None);bpy.context.collection.objects.link(root)

def finish(obj,mat,parent=root):
    obj.parent=parent;obj.data.materials.append(mat)
    for p in obj.data.polygons:p.use_smooth=True
    return obj

def sphere(name,at,scale,mat,parent=root):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,location=at)
    obj=bpy.context.object;obj.name=name;obj.scale=scale
    return finish(obj,mat,parent)

profile=[(.0,.06),(.43,.06),(.53,.11),(.55,.18),(.7,.23),(.92,.40),(1.1,.64),(1.23,.89),(1.25,1.0),(1.2,1.0),(1.15,.89),(.98,.58),(.65,.3),(.0,.25)]
vertices=[];faces=[];segments=64
for radius,z in profile:
    vertices.extend((radius*math.cos(i*math.tau/segments),radius*math.sin(i*math.tau/segments),z) for i in range(segments))
for j in range(len(profile)-1):
    for i in range(segments):
        n=(i+1)%segments;faces.append((j*segments+i,j*segments+n,(j+1)*segments+n,(j+1)*segments+i))
mesh=bpy.data.meshes.new('Lathed ceramic');mesh.from_pydata(vertices,[],faces);mesh.update()
body=bpy.data.objects.new('Ceramic',mesh);bpy.context.collection.objects.link(body);finish(body,charcoal)
bpy.ops.mesh.primitive_torus_add(major_radius=1.223,minor_radius=.038,major_segments=64,minor_segments=12,location=(0,0,.985))
finish(bpy.context.object,teal)
sphere('Soup',(0,0,.855),(1.13,1.13,.025),soup)

for x in [-.40,.40]:
    holder=bpy.data.objects.new('Blink',None);bpy.context.collection.objects.link(holder);holder.parent=root;holder.location=(x,-.985,.55)
    sphere('Cream eye',(0,-.028,0),(.18,.032,.18),cream,holder)
    sphere('Brown eye',(0,-.068,-.006),(.12,.025,.137),eye,holder)
    sphere('Pupil',(0,-.095,0),(.066,.012,.088),charcoal,holder)
    sphere('Sparkle',(-.027,-.111,.059),(.039,.01,.043),shine,holder)
    for frame,value in [(1,1),(23,1),(25,.08),(27,1),(48,1)]:
        holder.scale=(1,1,value);holder.keyframe_insert(data_path='scale',frame=frame)

def curve(name,points,mat,width):
    c=bpy.data.curves.new(name,'CURVE');c.dimensions='3D';c.bevel_depth=width;c.bevel_resolution=3
    s=c.splines.new('POLY');s.points.add(len(points)-1)
    for p,co in zip(s.points,points):p.co=(*co,1)
    obj=bpy.data.objects.new(name,c);bpy.context.collection.objects.link(obj);obj.parent=root;obj.data.materials.append(mat)

curve('Gentle smile',[(.26*math.cos(a),-1.037,.46+.12*math.sin(a)) for a in [math.pi+i*math.pi/24 for i in range(25)]],cream,.012)
curve('Noodle',[(.85*math.cos(a),.40*math.sin(a)+.07*math.sin(3*a),.892) for a in [i*math.tau/80 for i in range(81)]],cream,.014)
for frame,z,angle in [(1,0,0),(13,.03,-.025),(25,0,0),(37,.03,.025),(48,0,0)]:
    root.location.z=z;root.rotation_euler.z=angle
    root.keyframe_insert(data_path='location',frame=frame);root.keyframe_insert(data_path='rotation_euler',frame=frame)

scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=False
scene.render.resolution_x=144;scene.render.resolution_y=144;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.film_transparent=True
scene.render.fps=24;scene.frame_start=1;scene.frame_end=48
scene.world.color=(.3,.3,.3)
scene.view_settings.view_transform='Standard'
bpy.ops.object.camera_add(location=(0,-6,3.3))
cam=bpy.context.object;cam.rotation_euler=((Vector((0,0,.57))-cam.location).to_track_quat('-Z','Y').to_euler());cam.data.type='ORTHO';cam.data.ortho_scale=3.12;scene.camera=cam
for name,at,power,size in [('Softbox',(-3,-4,6),500,5),('Fill',(3,-2,3),180,4),('Rim',(0,3,4),300,3)]:
    bpy.ops.object.light_add(type='AREA',location=at);light=bpy.context.object;light.name=name;light.data.energy=power;light.data.shape='DISK';light.data.size=size
    light.rotation_euler=(Vector((0,0,.5))-light.location).to_track_quat('-Z','Y').to_euler()
scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(args.scene_file.resolve()))
# Keep full editable source outside the web build; ship only the small render.
frames=args.scene_file.parent/'cosoup-bowl-frames';frames.mkdir(exist_ok=True)
scene.render.filepath=str(frames/'bowl-')
bpy.ops.render.render(animation=True)
subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-framerate','24','-i',str(frames/'bowl-%04d.png'),'-c:v','libwebp_anim','-quality','80','-loop','0',str(args.output_dir/'bowl-idle.webp')],check=True)
subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(frames/'bowl-0001.png'),'-c:v','libwebp','-quality','85',str(args.output_dir/'bowl-poster.webp')],check=True)
print('Bowl loop and static reduced-motion poster exported.')
