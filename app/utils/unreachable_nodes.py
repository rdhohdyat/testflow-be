def detect_unreachable_code(cfg):
    if not cfg or isinstance(cfg, dict) and "message" in cfg:
        return []
    
    nodes = cfg["nodes"]
    edges = cfg["edges"]
    
    # Create a graph representation
    graph = {}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        
        if source not in graph:
            graph[source] = []
        
        graph[source].append(target)
    
    # Find reachable nodes using BFS from start node
    start_node = "1"  # Usually the Start node
    reachable = set()
    queue = [start_node]
    
    while queue:
        current = queue.pop(0)
        reachable.add(current)
        
        if current in graph:
            for neighbor in graph[current]:
                if neighbor not in reachable:
                    queue.append(neighbor)
    
    # Find unreachable nodes
    unreachable_nodes = []
    for node in nodes:
        node_id = node["id"]
        # Skip Start and End nodes
        if node["data"]["label"] not in ["Start", "End"] and node_id not in reachable:
            unreachable_nodes.append({
                "id": node_id,
                "line": node["data"]["lineno"],
                "code": node["data"]["tooltip"]
            })
    
    return unreachable_nodes