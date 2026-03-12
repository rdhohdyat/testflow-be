def generate_execution_paths(cfg):
    """
    Fungsi utama untuk menghasilkan daftar jalur eksekusi (jalur nomor baris) 
    berdasarkan Control Flow Graph (CFG) yang diberikan.
    """
    if not cfg or isinstance(cfg, dict) and "message" in cfg:
        return []

    nodes = cfg["nodes"]
    edges = cfg["edges"]

    # ---------------------------------------------------------------
    # A. Klasifikasi setiap Edge (Garis/Jalur)
    # ---------------------------------------------------------------
    # Memisahkan jalur yang merupakan "kembali ke atas" (loop back) 
    # dan jalur normal yang maju ke depan.
    back_edges: set = set()     # Untuk menyimpan (sumber, target) dari perulangan
    forward_edges: list = []    # Untuk menyimpan jalur maju biasa

    for edge in edges:
        src   = edge["source"]
        tgt   = edge["target"]
        label = (edge.get("label") or "")
        # Jika labelnya 'loop back', tandai sebagai jalur perulangan
        if label == "loop back":
            back_edges.add((src, tgt))
        else:
            forward_edges.append((src, tgt, label))

    # ---------------------------------------------------------------
    # B. Identifikasi Node Loop Header
    # ---------------------------------------------------------------
    # Loop header adalah node yang menjadi tujuan dari 'loop back' edge.
    # Ini adalah "pintu masuk" dari sebuah perulangan (seperti baris 'while' atau 'for').
    loop_nodes: set = set()
    for src, tgt in back_edges:
        loop_nodes.add(tgt)

    # ---------------------------------------------------------------
    # C. Bangun Struktur Graf
    # ---------------------------------------------------------------
    # fwd_graph  : Hanya berisi jalur maju (untuk mencegah perulangan tak terbatas)
    # full_graph : Berisi semua jalur termasuk loop back (untuk analisis lengkap)
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
    # Untuk setiap perulangan, kita perlu tahu ke mana arahnya jika 
    # kondisi perulangannya bernilai 'False' (jalur keluar).
    loop_exit: dict = {}   # loop_header_id → id_node_tujuan_keluar
    for lh in loop_nodes:
        # Jalur keluar biasanya adalah tetangga yang labelnya BUKAN "True"
        exits = [(nb, lbl) for nb, lbl in fwd_graph.get(lh, [])
                 if lbl.strip().lower() != "true"]
        if exits:
            loop_exit[lh] = exits[0][0]   # Ambil target pertama sebagai pintu keluar

    # ---------------------------------------------------------------
    # E. Augmented Forward Graph (Graf yang Diperluas)
    # ---------------------------------------------------------------
    # Kasus Khusus: Jika ada perintah 'if' di DALAM perulangan, dan jalur 'False'-nya 
    # adalah jalur 'loop back', kita bisa kehilangan opsi jalur tersebut di pencarian maju.
    # Di sini kita tambahkan "jalur virtual" langsung ke pintu keluar loop.
    aug_graph: dict = {nid: list(nbrs) for nid, nbrs in fwd_graph.items()}

    for src, tgt in back_edges:
        if tgt in loop_exit:
            loop_exit_node = loop_exit[tgt]
            # Tambahkan jalur dari titik akhir loop ke titik setelah loop selesai
            existing_targets = {nb for nb, _ in aug_graph.get(src, [])}
            if loop_exit_node not in existing_targets:
                aug_graph.setdefault(src, []).append(
                    (loop_exit_node, "")
                )

    # ---------------------------------------------------------------
    # F. Pemetaan ID Node ke Nomor Baris
    # ---------------------------------------------------------------
    # Mengambil data nomor baris dari setiap node untuk tampilan akhir.
    node_to_lines: dict = {}
    for node in nodes:
        nid  = node["id"]
        data = node.get("data", {})
        
        # Jika node hasil condense (punya banyak baris)
        if data.get("linenos"):
            node_to_lines[nid] = data["linenos"]
        elif data.get("lineno"):
            node_to_lines[nid] = [data["lineno"]]
        else:
            # Jika tidak ada nomor baris (misal 'Start'/'End'), gunakan labelnya
            node_to_lines[nid] = [data.get("label", "")]

    # ---------------------------------------------------------------
    # G. Tentukan Node Awal, Akhir, dan Hitung Cyclomatic Complexity
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

    # Hitung nilai Cyclomatic Complexity (V = E - N + 2) sebagai limit jalur
    v_complexity = len(edges) - len(nodes) + 2
    max_basis_paths = max(v_complexity, 1)

    # ---------------------------------------------------------------
    # H. Pencarian Jalur Keanggotaan Basis (Basis Path Testing)
    # ---------------------------------------------------------------
    all_raw_paths: list = []
    global_visited_edges: set = set() # Mencatat tepi (edge) yang sudah pernah dilalui

    def dfs(current: str, path: list, visited: set, loop_visits: dict):
        # Keamanan: Jika sudah mencapai limit basis path yang masuk akal, berhenti
        if len(all_raw_paths) >= max_basis_paths * 2: 
            return

        if current in loop_nodes:
            count = loop_visits.get(current, 0)
            if count >= 2: return
            new_lv = {**loop_visits, current: count + 1}
        else:
            if current in visited: return
            new_lv = loop_visits

        new_path    = path + [current]
        new_visited = visited | {current}

        if current in end_nodes:
            # --- LOGIKA BASIS PATH ---
            # Periksa apakah jalur ini melewati 'pintu' (edge) baru yang belum pernah dilihat
            is_new_basis_path = False
            for i in range(len(new_path) - 1):
                edge = (new_path[i], new_path[i+1])
                if edge not in global_visited_edges:
                    is_new_basis_path = True
                    break
            
            # Jika ini jalur baru yang unik secara struktur, simpan dan tandai edge-nya
            if is_new_basis_path:
                all_raw_paths.append(new_path)
                for i in range(len(new_path) - 1):
                    global_visited_edges.add((new_path[i], new_path[i+1]))
            return

        # Ambil tetangga (cabang)
        neighbors = aug_graph.get(current, [])
        
        # Urutkan: dahulukan tetangga yang edge-nya belum pernah dikunjungi (Greedy Basis)
        sorted_neighbors = sorted(
            neighbors, 
            key=lambda x: (current, x[0]) in global_visited_edges
        )

        for nb, lbl in sorted_neighbors:
            # Aturan kunjungan ke-2 untuk perulangan
            if current in loop_nodes and new_lv[current] == 2:
                if lbl.strip().lower() == "true": continue
            
            dfs(nb, new_path, new_visited, new_lv)

    # Mulai pencarian
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
            lines = node_to_lines.get(nid, [])
            for line in lines:
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

    # Pastikan jumlah hasil tidak meledak, urutkan berdasarkan panjang jalur
    return sorted(result, key=len)
