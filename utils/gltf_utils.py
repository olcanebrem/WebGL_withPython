def read_accessor_data(gltf_model, accessor_idx):
    accessor = gltf_model.accessors[accessor_idx]
    buffer_view = gltf_model.bufferViews[accessor.bufferView]
    buffer = gltf_model.buffers[buffer_view.buffer]

    # Veriyi getir
    raw_data = base64.b64decode(buffer.uri.split(",")[1])

    # Buffer'dan istenilen offset'e git
    start = buffer_view.byteOffset or 0
    if accessor.byteOffset:
        start += accessor.byteOffset
    count = accessor.count

    # Hangi tipte veri?
    component_type = accessor.componentType
    type_str = accessor.type  # VEC3, VEC4, SCALAR vs.

    # Veri formatı
    dtype_map = {
        5126: np.float32,  # FLOAT
        5123: np.uint16,   # UNSIGNED_SHORT
        5125: np.uint32,   # UNSIGNED_INT
    }

    if component_type not in dtype_map:
        raise ValueError(f"Desteklenmeyen component type: {component_type}")

    dtype = dtype_map[component_type]

    # Eleman başına kaç sayı?
    num_components = {
        'SCALAR': 1,
        'VEC2': 2,
        'VEC3': 3,
        'VEC4': 4,
        'MAT4': 16,
    }[type_str]

    # Veriyi oku
    data = np.frombuffer(raw_data[start:start + buffer_view.byteLength], dtype=dtype)
    data = data.reshape((count, num_components))
    return data

for channel in anim.channels:
    sampler = anim.samplers[channel.sampler]
    input_times = read_accessor_data(gltf_model, sampler.input)
    output_values = read_accessor_data(gltf_model, sampler.output)

    duration = input_times[-1][0] if input_times.ndim > 1 else input_times[-1]
    current_time = t % duration

    # İki keyframe arasında interpolasyon
    idx0 = np.searchsorted(input_times[:,0] if input_times.ndim > 1 else input_times, current_time) - 1
    idx0 = np.clip(idx0, 0, len(input_times) - 2)
    idx1 = idx0 + 1

    t0 = input_times[idx0][0] if input_times.ndim > 1 else input_times[idx0]
    t1 = input_times[idx1][0] if input_times.ndim > 1 else input_times[idx1]

    factor = (current_time - t0) / (t1 - t0) if (t1 - t0) != 0 else 0.0

    val0 = output_values[idx0]
    val1 = output_values[idx1]

    interp_val = (1.0 - factor) * val0 + factor * val1

    # Hangi node ve path?
    node_index = channel.target.node
    path = channel.target.path

    nodes = list(scene.graph.nodes)
    if node_index < len(nodes):
        node_name = nodes[node_index]
        node = scene.graph[node_name]

        mat = np.eye(4)

        if path == 'rotation':
            # Quaternion
            from scipy.spatial.transform import Rotation as R
            r = R.from_quat(interp_val)
            mat[:3,:3] = r.as_matrix()

        elif path == 'translation':
            mat[:3,3] = interp_val

        elif path == 'scale':
            mat[:3,0] *= interp_val[0]
            mat[:3,1] *= interp_val[1]
            mat[:3,2] *= interp_val[2]

        node.matrix = mat
