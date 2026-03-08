def generate_execution_paths(cfg):
    if not cfg or isinstance(cfg, dict) and "message" in cfg:
        return []

    nodes = cfg["nodes"]
    edges = cfg["edges"]

    # ---------------------------------------------------------------
    # A. Classify every edge
    # ---------------------------------------------------------------
    back_edges: set = set()     # (source, target) for "loop back" edges
    forward_edges: list = []    # all other edges

    for edge in edges:
        src   = edge["source"]
        tgt   = edge["target"]
        label = (edge.get("label") or "")
        if label == "loop back":
            back_edges.add((src, tgt))
        else:
            forward_edges.append((src, tgt, label))

    # ---------------------------------------------------------------
    # B. Loop-header nodes — any node that is the *target* of a
    #    loop-back edge.
    # ---------------------------------------------------------------
    loop_nodes: set = set()
    for src, tgt in back_edges:
        loop_nodes.add(tgt)

    # ---------------------------------------------------------------
    # C. Build two graphs:
    #
    #    fwd_graph   – only forward (non-loop-back) edges
    #    full_graph  – all edges (used to find the exit neighbor of a
    #                  loop header, i.e. where the loop jumps after it
    #                  finishes)
    # ---------------------------------------------------------------
    fwd_graph: dict  = {n["id"]: [] for n in nodes}
    full_graph: dict = {n["id"]: [] for n in nodes}

    for src, tgt, label in forward_edges:
        fwd_graph[src].append((tgt, label))
        full_graph[src].append((tgt, label))
    for src, tgt in back_edges:
        full_graph[src].append((tgt, "loop back"))

    # ---------------------------------------------------------------
    # D. For every loop header H, find its "exit successor":
    #    the neighbor reached via the non-True edge in fwd_graph.
    #    This is what the loop jumps to when the condition is False.
    # ---------------------------------------------------------------
    loop_exit: dict = {}   # loop_header_id → exit_node_id
    for lh in loop_nodes:
        exits = [(nb, lbl) for nb, lbl in fwd_graph.get(lh, [])
                 if lbl.strip().lower() != "true"]
        if exits:
            loop_exit[lh] = exits[0][0]   # first non-True successor

    # ---------------------------------------------------------------
    # E. Augmented forward graph
    #
    #    Problem: an `if`-node INSIDE a loop may have its False branch
    #    as a "loop back" edge.  When we filter loop-back edges we lose
    #    the False alternative.  We re-add it as a "virtual" edge
    #    directly to the loop's exit node so the DFS can see both
    #    branches of the inner if.
    # ---------------------------------------------------------------
    aug_graph: dict = {nid: list(nbrs) for nid, nbrs in fwd_graph.items()}

    for src, tgt in back_edges:
        # src has a back-edge to loop header `tgt`.
        # If src also has forward edges (i.e. it's not just the loop
        # body's final statement) skip — it already has an exit route.
        # The interesting case: src has a back-edge to tgt (loop header)
        # AND that back-edge represents the "False / skip body" path.
        # We redirect it to the loop's own exit.
        if tgt in loop_exit:
            loop_exit_node = loop_exit[tgt]
            # Only add the virtual edge if src doesn't already have a
            # forward edge to the same destination (avoid duplicates).
            existing_targets = {nb for nb, _ in aug_graph.get(src, [])}
            if loop_exit_node not in existing_targets:
                aug_graph.setdefault(src, []).append(
                    (loop_exit_node, "")
                )

    # ---------------------------------------------------------------
    # F. node-id → display line number
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
    # G. Start / end nodes
    # ---------------------------------------------------------------
    start_node = "1"

    end_nodes: set = set()
    for node in nodes:
        nid = node["id"]
        label = node.get("data", {}).get("label", "")
        if label == "End":
            end_nodes.add(nid)
    # Also consider sink nodes (no forward edges at all)
    for nid in [n["id"] for n in nodes]:
        if nid not in aug_graph or not aug_graph[nid]:
            end_nodes.add(nid)

    # ---------------------------------------------------------------
    # H. DFS on the augmented forward graph
    #
    #   • Loop-header nodes: allow at most 2 visits per path.
    #     – 1st visit: explore ALL forward edges (True → body, False → exit)
    #     – 2nd visit: explore ONLY the exit (non-True) edge
    #   • All other nodes: at most 1 visit (simple DFS).
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

        # 2nd visit to a loop header: only follow exit edges
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
    # I. Convert to line-number paths and deduplicate
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