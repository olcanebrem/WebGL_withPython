import numpy as np
import base64
import threading
import time
from flask import Flask, render_template
import pyrender
import trimesh
from PIL import Image
import io

app = Flask(__name__)

# Global frame buffer for thread-safe sharing
latest_frame = None
frame_width = 800
frame_height = 600
frame_lock = threading.Lock()  # Lock for thread-safe access to latest_frame

# Animasyon state
model_angle = 0.0  # fallback için
model_angle_lock = threading.Lock()
active_animation_index = None  # Oynatılan animasyonun index'i
animation_start_time = None   # Oynatılmaya başlanan zaman
animation_lock = threading.Lock()
gltf_animations = []  # Animasyon verileri

# Orbit kamera state
global_orbit_angle = 0.0
orbit_angle_lock = threading.Lock()
camera_node = None
# Model yükleyici ve sahne oluşturucu
def load_gltf_scene():
    global gltf_animations, camera_node
    print("Model yükleniyor...")
    mesh = trimesh.load('static/model.glb')
    print("Model tipi:", type(mesh))
    print("Mesh summary:", mesh)
    # Animasyonları al
    print('mesh.animations:', getattr(mesh, 'animations', None))
    print('mesh type:', type(mesh))
    print('mesh dir:', dir(mesh))
    if hasattr(mesh, 'animations') and mesh.animations:
        gltf_animations = mesh.animations
        print(f"Animasyonlar bulundu: {len(gltf_animations)} adet")
        for i, anim in enumerate(gltf_animations):
            print(f"Animasyon {i}: {anim}")
        # Eğer sadece bir animasyon varsa, otomatik başlat
        if len(gltf_animations) == 1:
            global active_animation_index, animation_start_time
            active_animation_index = 0
            animation_start_time = time.time()
    else:
        print("Animasyon bulunamadı.")
    scene = pyrender.Scene()
    if isinstance(mesh, trimesh.Scene):
        for name, geometry in mesh.geometry.items():
            scene.add(pyrender.Mesh.from_trimesh(geometry))
    else:
        scene.add(pyrender.Mesh.from_trimesh(mesh))
    # Daha belirgin bir ışık ekle
    light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=5.0)
    scene.add(light, pose=[[1,0,0,0],[0,1,0,5],[0,0,1,5],[0,0,0,1]])
    # Kamerayı daha yukarıdan ve uzaktan bakacak şekilde ayarla
    camera = pyrender.PerspectiveCamera(yfov=np.pi/3.0)
    camera_pose = np.array([[1,0,0,0],[0,1,0,2],[0,0,1,6],[0,0,0,1]])
    camera_node = scene.add(camera, pose=camera_pose)
    return scene

# Offscreen renderer for Flask
def flask_render_loop(scene):
    global latest_frame, model_angle, active_animation_index, animation_start_time, gltf_animations, global_orbit_angle, camera_node
    renderer = pyrender.OffscreenRenderer(frame_width, frame_height)
    mesh_nodes = [node for node in scene.get_nodes() if isinstance(node.mesh, pyrender.Mesh)]
    mesh_node = mesh_nodes[0] if mesh_nodes else None
    import time as _time
    while True:
        # Kamera orbit pozisyonu
        with orbit_angle_lock:
            orbit_angle = global_orbit_angle
        radius = 6.0
        height = 2.0
        cam_x = radius * np.sin(orbit_angle)
        cam_z = radius * np.cos(orbit_angle)
        camera_pose = np.array([
            [1, 0, 0, cam_x],
            [0, 1, 0, height],
            [0, 0, 1, cam_z],
            [0, 0, 0, 1]
        ])
        if camera_node is not None:
            scene.set_pose(camera_node, pose=camera_pose)
        # Animasyon oynatılıyor mu?
        with animation_lock:
            anim_idx = active_animation_index
            anim_start = animation_start_time
        if anim_idx is not None and anim_idx < len(gltf_animations):
            anim = gltf_animations[anim_idx]
            duration = anim['channels'][0]['sampler']['input'][-1] if anim['channels'] else 1.0
            now = _time.time()
            t = ((now - anim_start) % duration) if anim_start else 0.0
            for ch in anim['channels']:
                node_idx = ch['target']['node']
                path = ch['target']['path']
                sampler = ch['sampler']
                input_times = sampler['input']
                output_vals = sampler['output']
                idx = min(range(len(input_times)), key=lambda i: abs(input_times[i] - t))
                val = output_vals[idx]
                nodes = list(scene.graph.nodes)
                if node_idx < len(nodes):
                    node_name = nodes[node_idx]
                    if path == 'rotation':
                        from scipy.spatial.transform import Rotation as R
                        quat = val
                        rot = R.from_quat([quat[0], quat[1], quat[2], quat[3]]).as_matrix()
                        mat = np.eye(4)
                        mat[:3,:3] = rot
                        scene.graph[node_name].matrix = mat
                    elif path == 'translation':
                        mat = np.eye(4)
                        mat[:3,3] = val
                        scene.graph[node_name].matrix = mat
                    elif path == 'scale':
                        mat = np.eye(4)
                        mat[0,0], mat[1,1], mat[2,2] = val
                        scene.graph[node_name].matrix = mat
        color, _ = renderer.render(scene)
        image = Image.fromarray(color)
        if not hasattr(flask_render_loop, "saved"): 
            image.save("debug_render.png")
            flask_render_loop.saved = True
        frame_data = base64.b64encode(color.tobytes()).decode('utf-8')

        with frame_lock:
            latest_frame = frame_data  # Thread-safe write to latest_frame
        time.sleep(0.05)

@app.route('/')
def index():
    return render_template('index.html')  # HTML dosyanızın adı

@app.route('/render_frame')
def render_frame():
    global latest_frame
    if latest_frame is None:
        return {'width': frame_width, 'height': frame_height, 'image': ''}
    
    return {'width': frame_width, 'height': frame_height, 'image': latest_frame}

@app.route('/key_event/<key>', methods=['POST'])
def key_event(key):
    print(f"Key event received: {key}")
    global model_angle, active_animation_index, animation_start_time, global_orbit_angle
    # Tuşa göre animasyon ata (ör: q=0, w=1)
    if key == 'q':
        with animation_lock:
            active_animation_index = 0
            animation_start_time = __import__('time').time()
    elif key == 'w':
        with animation_lock:
            active_animation_index = 1
            animation_start_time = __import__('time').time()
    elif key == 'a':
        with orbit_angle_lock:
            global_orbit_angle -= 0.1
    elif key == 'd':
        with orbit_angle_lock:
            global_orbit_angle += 0.1
    return '', 204

if __name__ == '__main__':
    scene = load_gltf_scene()
    t = threading.Thread(target=flask_render_loop, args=(scene,), daemon=True)
    t.start()
    app.run(debug=True, use_reloader=False)
