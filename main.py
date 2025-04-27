import numpy as np
import base64
import threading
import time
from flask import Flask, render_template
import pyrender
import trimesh
from pygltflib import GLTF2
from PIL import Image
import numpy as np
import struct
import os
import math

app = Flask(__name__)

# Global değişkenler
latest_frame = None
frame_width = 800
frame_height = 600
frame_lock = threading.Lock()

# Animasyon state
global_orbit_angle = 0.0
orbit_angle_lock = threading.Lock()
camera_node = None

# Animasyon datası
gltf_model = None
gltf_animations = []
glb_buffer_bytes = None
animation_start_time = None
active_animation_index = None
animation_lock = threading.Lock()

def load_gltf_scene():
    global gltf_model, gltf_animations, camera_node, glb_buffer_bytes

    print("Model yükleniyor...")
    # Geometriyi yükle
    mesh = trimesh.load('static/model.glb')

    # GLTF ham veriyi yükle
    gltf_model = GLTF2().load('static/model.glb')

    # GLB buffer'ı oku
    with open('static/model.glb', 'rb') as f:
        glb_buffer_bytes = f.read()

    # Animasyonları al
    gltf_animations = gltf_model.animations or []
    print(f"{len(gltf_animations)} adet animasyon bulundu.")

    # Scene oluştur
    scene = pyrender.Scene()
    if isinstance(mesh, trimesh.Scene):
        for name, geometry in mesh.geometry.items():
            scene.add(pyrender.Mesh.from_trimesh(geometry))
    else:
        scene.add(pyrender.Mesh.from_trimesh(mesh))

    # Işık ve kamera ekle
    light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=5.0)
    scene.add(light, pose=np.eye(4))

    camera = pyrender.PerspectiveCamera(yfov=np.pi/3.0)
    camera_pose = np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 2],
        [0, 0, 1, 6],
        [0, 0, 0, 1],
    ])
    camera_node = scene.add(camera, pose=camera_pose)

    return scene

def read_accessor_data(gltf, accessor_idx, glb_buffer_bytes):
    accessor = gltf.accessors[accessor_idx]
    buffer_view = gltf.bufferViews[accessor.bufferView]
    buffer_offset = buffer_view.byteOffset or 0
    accessor_offset = accessor.byteOffset or 0
    total_offset = buffer_offset + accessor_offset
    count = accessor.count
    dtype = np.float32 if accessor.componentType == 5126 else np.uint16  # 5126: FLOAT, 5123: UNSIGNED_SHORT
    ncomp = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4}[accessor.type]
    total_bytes = count * ncomp * np.dtype(dtype).itemsize
    # GLB'de JSON + BIN chunk offseti olabilir, buffer_view.byteOffset genelde doğrudur
    data = glb_buffer_bytes[total_offset:total_offset+total_bytes]
    arr = np.frombuffer(data, dtype=dtype, count=count*ncomp)
    arr = arr.reshape((count, ncomp))
    return arr

def flask_render_loop(scene):
    global latest_frame, animation_start_time, active_animation_index
    renderer = pyrender.OffscreenRenderer(frame_width, frame_height)

    while True:
        with orbit_angle_lock:
            y_angle = global_orbit_angle
        from scipy.spatial.transform import Rotation as R
        user_rot_y = R.from_euler('y', y_angle).as_matrix()
        user_rot_mat = np.eye(4)
        user_rot_mat[:3, :3] = user_rot_y

        # Animasyonu uygula
        with animation_lock:
            idx = active_animation_index
            start_time = animation_start_time

        # Node'lara dönüşleri uygula
        for node in scene.get_nodes():
            if hasattr(node, 'mesh') and node.mesh is not None:
                anim_applied = False
                if idx is not None and start_time is not None and idx < len(gltf_animations):
                    anim = gltf_animations[idx]
                    now = time.time()
                    t = (now - start_time)
                    for channel in anim.channels:
                        sampler = anim.samplers[channel.sampler]
                        # Input (keyframe times)
                        input_times = read_accessor_data(gltf_model, sampler.input, glb_buffer_bytes).flatten()
                        # Output (values)
                        output_vals = read_accessor_data(gltf_model, sampler.output, glb_buffer_bytes)
                        # Animasyonun node'u doğruysa uygula
                        if channel.target.node == node.name and channel.target.path == 'rotation':
                            # GLTF'de quaternion (x, y, z, w)
                            from scipy.spatial.transform import Rotation as R
                            # En yakın keyframe'i bul
                            idx_frame = np.searchsorted(input_times, t, side='right') - 1
                            if idx_frame < 0:
                                idx_frame = 0
                            quat = output_vals[idx_frame]
                            anim_rot = R.from_quat(quat).as_matrix()
                            anim_mat = np.eye(4)
                            anim_mat[:3, :3] = anim_rot
                            # Kullanıcı dönüşüyle birleştir
                            final_mat = np.matmul(anim_mat, user_rot_mat)
                            scene.set_pose(node, pose=final_mat)
                            anim_applied = True
                if not anim_applied:
                    # Sadece kullanıcı dönüşünü uygula
                    scene.set_pose(node, pose=user_rot_mat)

        # Frame çizimi
        color, _ = renderer.render(scene)
        image = Image.fromarray(color)
        frame_data = base64.b64encode(color.tobytes()).decode('utf-8')

        with frame_lock:
            latest_frame = frame_data

        time.sleep(0.05)

        with frame_lock:
            latest_frame = frame_data

        time.sleep(0.05)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/render_frame')
def render_frame():
    global latest_frame
    if latest_frame is None:
        return {'width': frame_width, 'height': frame_height, 'image': ''}
    return {'width': frame_width, 'height': frame_height, 'image': latest_frame}

@app.route('/key_event/<key>', methods=['POST'])
def key_event(key):
    global global_orbit_angle
    if key == 'q':
        with orbit_angle_lock:
            global_orbit_angle -= math.radians(15)
    elif key == 'w':
        with orbit_angle_lock:
            global_orbit_angle += math.radians(15)
    return ('', 204)

if __name__ == '__main__':
    scene = load_gltf_scene()
    t = threading.Thread(target=flask_render_loop, args=(scene,), daemon=True)
    t.start()
    app.run(debug=True, use_reloader=False)
