def generate_execution_paths(cfg):
    """
    Fungsi utama untuk menghasilkan daftar jalur eksekusi (jalur nomor baris) 
    berdasarkan Control Flow Graph (CFG) yang diberikan.
    
    VERSI LAMA: Menggunakan pencarian semua kemungkinan jalur (All Paths).
    Dapat menyebabkan Path Explosion pada kode yang kompleks.
    """
    if not cfg or isinstance(cfg, dict) and "message" in cfg:
        return []

    nodes = cfg["nodes"]
    edges = cfg["edges"]

    # ---------------------------------------------------------------
    # A. Klasifikasi setiap Edge (Garis/Jalur)
    # ---------------------------------------------------------------
    back_edges: set = set()     # Untuk menyimpan (sumber, target) dari perulangan
    forward_edges: list = []    # Untuk menyimpan jalur maju biasa

    for edge in edges:
        src   = edge["source"]
        tgt   = edge["target"]
        label = (edge.get("label") or "")
        if label == "loop back":
            back_edges.add((src, tgt))
        else:
            forward_edges.append((src, tgt, label))

    # ---------------------------------------------------------------
    # B. Identifikasi Node Loop Header
    # ---------------------------------------------------------------
    loop_nodes: set = set()
    for src, tgt in back_edges:
        loop_nodes.add(tgt)

    # ---------------------------------------------------------------
    # C. Bangun Struktur Graf
    # ---------------------------------------------------------------
    fwd_graph: dict  = {n["id"]: [] for n in nodes}
    full_graph: dict = {n["id"]: [] for n in nodes}

    for src, tgt, label in forward_edges:
        fwd_graph[src].append((tgt, label))
        full_graph[src].append((tgt, label))
    for src, tgt in back_edges:
        full_graph[src].append((tgt, "loop back"))

    # ---------------------------------------------------------------
    # D. Cari "Jalur Keluar" untuk setiap Loop Header
    # ---------------------------------------------------------------
    loop_exit: dict = {}   # loop_header_id → id_node_tujuan_keluar
    for lh in loop_nodes:
        exits = [(nb, lbl) for nb, lbl in fwd_graph.get(lh, [])
                 if lbl.strip().lower() != "true"]
        if exits:
            loop_exit[lh] = exits[0][0]

    # ---------------------------------------------------------------
    # E. Augmented Forward Graph (Graf yang Diperluas)
    # ---------------------------------------------------------------
    aug_graph: dict = {nid: list(nbrs) for nid, nbrs in fwd_graph.items()}

    for src, tgt in back_edges:
        if tgt in loop_exit:
            loop_exit_node = loop_exit[tgt]
            existing_targets = {nb for nb, _ in aug_graph.get(src, [])}
            if loop_exit_node not in existing_targets:
                aug_graph.setdefault(src, []).append(
                    (loop_exit_node, "")
                )

    # ---------------------------------------------------------------
    # F. Pemetaan ID Node ke Nomor Baris
    # ---------------------------------------------------------------
    node_to_line: dict = {}
    for node in nodes:
        nid  = node["id"]
        data = node.get("data", {})
        if data.get("lineno"):
            node_to_line[nid] = data["lineno"]
        else:
            node_to_line[nid] = data.get("label", "")

    # ---------------------------------------------------------------
    # G. Tentukan Node Awal dan Akhir
    # ---------------------------------------------------------------
    start_node = "1"

    end_nodes: set = set()
    for node in nodes:
        nid = node["id"]
        label = node.get("data", {}).get("label", "")
        if label == "End":
            end_nodes.add(nid)
    
    for nid in [n["id"] for n in nodes]:
        if nid not in aug_graph or not aug_graph[nid]:
            end_nodes.add(nid)

    # ---------------------------------------------------------------
    # H. Pencarian Jalur Mendalam (DFS - Depth First Search)
    # ---------------------------------------------------------------
    all_raw_paths: list = []

    def dfs(current: str, path: list, visited: set, loop_visits: dict):
        if current in loop_nodes:
            count = loop_visits.get(current, 0)
            if count >= 2:
                return
            new_lv = {**loop_visits, current: count + 1}
        else:
            if current in visited:
                return
            new_lv = loop_visits

        new_path    = path + [current]
        new_visited = visited | {current}

        if current in end_nodes:
            all_raw_paths.append(new_path)
            return

        neighbors = aug_graph.get(current, [])
        if not neighbors:
            all_raw_paths.append(new_path)
            return

        if current in loop_nodes and new_lv[current] == 2:
            explore = [(nb, lbl) for nb, lbl in neighbors
                       if lbl.strip().lower() != "true"]
            if not explore:
                explore = neighbors
        else:
            explore = neighbors

        for nb, _ in explore:
            dfs(nb, new_path, new_visited, new_lv)

    dfs(start_node, [], set(), {})

    # ---------------------------------------------------------------
    # I. Konversi ke Nomor Baris dan Hapus Jalur Duplikat
    # ---------------------------------------------------------------
    seen_keys: set = set()
    result: list = []

    SKIP_LABELS = {"Start", "End", "After while", "After for"}

    for node_path in all_raw_paths:
        line_path = []
        for nid in node_path:
            line = node_to_line.get(nid)
            if (line is not None
                    and line not in SKIP_LABELS
                    and (isinstance(line, int)
                         or (isinstance(line, str) and str(line).isdigit()))):
                line_path.append(str(line))

        if not line_path:
            continue

        key = tuple(line_path)
        if key not in seen_keys:
            seen_keys.add(key)
            result.append(line_path)

    return result
