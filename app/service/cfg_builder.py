import ast
from typing import List, Dict, Any, Tuple, Set, Optional, Union

def condense_cfg(nodes, edges):
    """
    Groups sequential nodes (chains) into a single display node.
    Example: 1 -> 2 -> 3 becomes [1-3].
    Condition: 
    - u has exactly one outgoing edge (to v)
    - v has exactly one incoming edge (from u)
    - Both are simple statements (no branching/looping types)
    """
    if not nodes:
        return nodes, edges

    # Mapping for quick lookup
    nodes_dict = {n["id"]: n for n in nodes}
    
    # Types that are safe to merge
    MERGEABLE_TYPES = {"statement", "assignment", "expression", "call", "default"}

    def get_adj_maps(current_edges):
        out_map = {}
        in_map = {}
        for e in current_edges:
            s, t = e["source"], e["target"]
            out_map.setdefault(s, []).append(t)
            in_map.setdefault(t, []).append(s)
        return out_map, in_map

    modified = True
    while modified:
        modified = False
        out_map, in_map = get_adj_maps(edges)
        
        for e in edges:
            u_id, v_id = e["source"], e["target"]
            
            # 1. Check if u and v exist
            if u_id not in nodes_dict or v_id not in nodes_dict:
                continue
                
            u = nodes_dict[u_id]
            v = nodes_dict[v_id]
            
            # 2. Check sequential integrity
            # u must have ONLY ONE outgoing edge (to v)
            if len(out_map.get(u_id, [])) != 1 or out_map[u_id][0] != v_id:
                continue
            # v must have ONLY ONE incoming edge (from u)
            if len(in_map.get(v_id, [])) != 1 or in_map[v_id][0] != u_id:
                continue
                
            # 3. Check types
            u_type = u["data"].get("node_type")
            v_type = v["data"].get("node_type")
            if u_type not in MERGEABLE_TYPES or v_type not in MERGEABLE_TYPES:
                continue
                
            # 4. Check labels on the edge
            if e.get("label"): # Don't merge if there's a label (e.g., True/False/loop back)
                continue
                
            # 5. Check if they have line numbers
            u_line = u["data"].get("lineno")
            v_line = v["data"].get("lineno")
            if u_line is None or v_line is None:
                continue

            # PERFORM MERGE
            # Update line numbers track
            u_lines = u["data"].get("linenos")
            if u_lines is None:
                u_lines = [u_line]
            
            v_lines = v["data"].get("linenos")
            if v_lines is None:
                v_lines = [v_line]
                
            combined_lines = u_lines + v_lines
            u["data"]["linenos"] = combined_lines
            u["data"]["label"] = f"{combined_lines[0]} - {combined_lines[-1]}"
            u["data"]["tooltip"] = u["data"]["tooltip"] + "\n" + v["data"]["tooltip"]
            
            # Remove the edge u -> v
            edges = [edge for edge in edges if not (edge["source"] == u_id and edge["target"] == v_id)]
            
            # Redirect all edges coming OUT of v to come OUT of u instead
            for edge in edges:
                if edge["source"] == v_id:
                    edge["source"] = u_id
                    # Update edge ID to be unique
                    edge["id"] = f"e{edge['source']}-{edge['target']}"
            
            # Remove node v
            nodes = [n for n in nodes if n["id"] != v_id]
            del nodes_dict[v_id]
            
            modified = True
            break # Re-calculate maps for next iteration
            
    return nodes, edges

def build_cfg(code: str):
    try:
        tree = ast.parse(code)
        nodes, edges, parameters = extract_cfg(tree)
        
        # Post-process to condense sequential nodes
        nodes, edges = condense_cfg(nodes, edges)
        
        return {
            "nodes": nodes,
            "edges": edges,
            "parameters": parameters
        }
    except Exception as e:
        return {"message": f"Error parsing code: {str(e)}"}


def get_operator_symbol(op):
    """Convert AST operator to symbol"""
    op_map = {
        ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/',
        ast.Mod: '%', ast.Pow: '**', ast.LShift: '<<', ast.RShift: '>>',
        ast.BitOr: '|', ast.BitXor: '^', ast.BitAnd: '&', ast.FloorDiv: '//'
    }
    return op_map.get(type(op), '?')

def get_exit_nodes(result):
    """Return actual exit nodes from a visit result (especially if it's an if structure)"""
    if isinstance(result, dict) and "if_node" in result:
        exit_nodes = []
        if result.get("true_end") != result["if_node"]:
            exit_nodes.append(result["true_end"])
        if result.get("has_else") and result.get("false_end") != result["if_node"]:
            exit_nodes.append(result["false_end"])
        return exit_nodes
    else:
        return [result]

    
def extract_cfg(tree):
    nodes = []
    edges = []
    parameters = []
    node_id = 1
    last_nodes = []
    
    # Visual layout settings
    x_offset = 450
    y_spacing = 80
    x_spacing = 100
    
    # Track loops and control structures
    loop_stack = []
    try_blocks = {}
    visited_lines = set()
    

    def add_node(label, lineno=None, pos=None, node_type="default"):
        nonlocal node_id

        if pos is None:
            pos = get_position()
   
        tooltip = label
        display_text = str(lineno) if lineno else label
        
        node = {
            "id": str(node_id),
            "type": "custom",
            "position": pos,
            "data": {
                "label": display_text, 
                "tooltip": tooltip,     
                "lineno": lineno,     
                "node_type": node_type  
            }
        }
        nodes.append(node)
        node_id += 1
        
        if lineno:
            visited_lines.add(lineno)
            
        return str(node_id - 1)

    def create_edge(source, target, label=None, is_loop=False, edge_type="default"):
        if source == target:  # Avoid self-loops
            return
            
        # === MODIFIKASI: Cek edge yang sudah ada & UPDATE labelnya ===
        existing_edge = next((e for e in edges if e["source"] == str(source) and e["target"] == str(target)), None)
        
        if existing_edge:
            # Jika edge sudah ada, tapi kita ingin memberi label baru (misal True/False)
            if label and not existing_edge.get("label"):
                existing_edge["label"] = label
                # Update warna jika perlu
                if edge_type == "true":
                    existing_edge["style"]["stroke"] = "#2ECC71"
                elif edge_type == "false":
                    existing_edge["style"]["stroke"] = "#EF4444"
            return
        # ==============================================================
            
        edge_style = {
            "strokeWidth": 2, 
            "stroke": "#000000"
        }
        
        if is_loop:
            edge_style["stroke"] = "#E74C3C"  # Red color for loop edges
            edge_style["animated"] = True
            edge_style["strokeWidth"] = 3
        elif edge_type == "exception":
            edge_style["stroke"] = "#F39C12"  # Orange for exception flow
            edge_style["strokeDasharray"] = "5,5"
        elif edge_type == "true":
            edge_style["stroke"] = "#2ECC71"  # Green for true conditions
        elif edge_type == "false":
            edge_style["stroke"] = "#EF4444"  # Red for false conditions (Ganti ke Merah agar sesuai frontend)
        
        # FIXED: Always include label if provided
        edge_data = {
            "id": f"e{source}-{target}",
            "source": str(source),
            "target": str(target),
            "markerEnd": {"type": "arrowclosed", "color": edge_style["stroke"]},
            "style": edge_style
        }
        
        # Add label if provided
        if label:
            edge_data["label"] = label
            
        edges.append(edge_data)

    def get_pos(branch_index=0, is_else=False):
        """Simple y increment for horizontal neatness, symmetric x shift."""
        y = (len(nodes) + 1) * 80
        branch_offset = 120
        if is_else:
            x = x_offset - branch_offset
        elif branch_index > 0:
            x = x_offset + (branch_index * branch_offset)
        else:
            x = x_offset
        return {"x": x, "y": y}

    def visit(node, parent_ids, depth=0, branch_index=0, is_else=False):
        """Universal visit that handles multiple parents and returns multiple exits."""
        
        if isinstance(node, ast.FunctionDef):
            # Header
            param_list = [str(arg.arg) for arg in node.args.args]
            parameters.append({"function": node.name, "params": param_list})
            param_str = ", ".join(param_list) if param_list else ""
            label = f"def {node.name}({param_str}):"
            
            func_id = add_node(label, node.lineno, get_pos(branch_index, is_else), "function")
            for p in parent_ids:
                create_edge(p, func_id)
            
            # Body paths
            body_exits = [func_id]
            for stmt in node.body:
                body_exits = visit(stmt, body_exits, depth + 1, branch_index + 1)
            
            # Connect body to End separately
            last_nodes.extend(body_exits)
            
            # Return header as the "flow-through" for the definition itself
            return [func_id]

        elif isinstance(node, ast.If):
            cond = ast.unparse(node.test)
            if_id = add_node(f"if {cond}:", node.lineno, get_pos(branch_index, is_else), "condition")
            for p in parent_ids:
                create_edge(p, if_id)
            
            # True branch
            true_exits = visit_block(node.body, [if_id], depth + 1, branch_index + 1, False, "True")
            
            # False branch
            if node.orelse:
                false_exits = visit_block(node.orelse, [if_id], depth + 1, branch_index, True, "False")
                return true_exits + false_exits
            else:
                # No else, if_id itself is the false exit
                return true_exits + [if_id]

        elif isinstance(node, ast.While) or isinstance(node, ast.For):
            if isinstance(node, ast.While):
                cond = ast.unparse(node.test)
                label = f"while {cond}:"
            else:
                t = ast.unparse(node.target)
                it = ast.unparse(node.iter)
                label = f"for {t} in {it}:"
            
            loop_id = add_node(label, node.lineno, get_pos(branch_index, is_else), "loop")
            for p in parent_ids:
                create_edge(p, loop_id)
            
            loop_stack.append(loop_id)
            
            # Body branches back to header
            body_exits = visit_block(node.body, [loop_id], depth + 1, branch_index + 1, False, "True")
            for b in body_exits:
                create_edge(b, loop_id, "loop back", True, "loop")
                
            loop_stack.pop()
            return [loop_id] # Exit is always header (False path)

        elif isinstance(node, ast.Return):
            val = ast.unparse(node.value) if node.value else ""
            ret_id = add_node(f"return {val}", node.lineno, get_pos(branch_index, is_else), "return")
            for p in parent_ids:
                create_edge(p, ret_id)
            last_nodes.append(ret_id)
            return [] # Returns DIE here

        elif isinstance(node, ast.Match):
            # Python 3.10+ match/case statement
            subject = ast.unparse(node.subject)
            match_id = add_node(f"match {subject}:", node.lineno, get_pos(branch_index, is_else), "condition")
            for p in parent_ids:
                create_edge(p, match_id)

            all_case_exits = []
            for i, case in enumerate(node.cases):
                # Build a human-readable label for the pattern
                try:
                    pattern_str = ast.unparse(case.pattern)
                except Exception:
                    pattern_str = f"case {i}"

                # Wildcard pattern `case _:` → label as "default"
                if pattern_str == "_":
                    case_label = "default"
                else:
                    case_label = f"case {pattern_str}"

                # Each case body is a branch off the match node
                case_exits = visit_block(
                    case.body, [match_id], depth + 1,
                    branch_index + i + 1, i % 2 == 1, case_label
                )
                all_case_exits.extend(case_exits)

            # If no wildcard/default case exists, the match node itself
            # is also an exit (no case matched → fall through)
            has_wildcard = any(
                (ast.unparse(c.pattern) if hasattr(c, 'pattern') else '') in ('_', '')
                for c in node.cases
            )
            if not has_wildcard:
                all_case_exits.append(match_id)

            return all_case_exits if all_case_exits else [match_id]

        elif isinstance(node, ast.Break):
            break_id = add_node("break", node.lineno, get_pos(branch_index, is_else), "break")
            for p in parent_ids:
                create_edge(p, break_id)
            # Should connect to loop exit, but we handle via last_nodes for now
            last_nodes.append(break_id)
            return []

        elif isinstance(node, ast.Continue):
            cont_id = add_node("continue", node.lineno, get_pos(branch_index, is_else), "continue")
            for p in parent_ids:
                create_edge(p, cont_id)
            if loop_stack:
                create_edge(cont_id, loop_stack[-1], "loop back", True, "loop")
            return []

        # Simple statements
        else:
            try:
                label = ast.unparse(node)
            except:
                label = f"{type(node).__name__}"
            
            style_type = "statement"
            if isinstance(node, (ast.Assign, ast.AugAssign)): style_type = "assignment"
            elif isinstance(node, ast.Expr): style_type = "expression"
            elif isinstance(node, ast.Call): style_type = "call"
            
            node_id = add_node(label, getattr(node, 'lineno', None), get_pos(branch_index, is_else), style_type)
            for p in parent_ids:
                create_edge(p, node_id)
            return [node_id]

    def visit_block(stmts, entering_ids, depth, branch_index, is_else, first_label=None):
        current_ids = entering_ids
        for i, stmt in enumerate(stmts):
            # Special case for labeling the first stmt of a branch
            if i == 0 and first_label:
                # We need to intercept create_edge calls inside visit for the first stmt?
                # No, visit will call create_edge. We can't easily label it from here.
                # Let's pass the label to visit? Too complex.
                # Solution: Pre-create a node for the first stmt? No.
                # Let's just track the last edge index.
                old_edge_count = len(edges)
                current_ids = visit(stmt, current_ids, depth, branch_index, is_else)
                for idx in range(old_edge_count, len(edges)):
                    if edges[idx]["source"] in entering_ids:
                        edges[idx]["label"] = first_label
                        edges[idx]["type"] = "straight"
                        edges[idx]["edge_type"] = "true" if first_label == "True" else "false"
            else:
                current_ids = visit(stmt, current_ids, depth, branch_index, is_else)
        return current_ids

    # Start Node
    start_id = add_node("Start", None, {"x": x_offset, "y": 50}, "control")
    
    # Process all root-level statements
    final_exits = visit_block(tree.body, [start_id], 0, 0, False)
    
    # Filter out function definitions from being the SOLE exit of the file
    # (to avoid the "Path: 1" issue where it just defines the function and ends)
    for exit_id in final_exits:
        node_idx = int(exit_id) - 1
        if nodes[node_idx]["data"].get("node_type") != "function":
            last_nodes.append(exit_id)
        else:
            # If a function is the last thing, we still want it to connect to End 
            # ONLY IF there are no other paths? No, usually we want to see body paths.
            # If we don't add it, the "Start -> Header -> End" path is removed. Correct.
            pass

    # End Node
    if nodes:
        end_pos = {"x": x_offset, "y": (len(nodes) + 1) * 80}
        end_id = add_node("End", None, end_pos, "control")
        
        seen_edges = set()
        for final_node in last_nodes:
            if final_node and final_node != end_id and (final_node, end_id) not in seen_edges:
                # Check if it was a condition/loop to add "False" label
                lbl = ""
                for n in nodes:
                    if n["id"] == final_node and n["data"]["node_type"] in ["condition", "loop"]:
                        lbl = "False"
                        break
                create_edge(final_node, end_id, lbl)
                seen_edges.add((final_node, end_id))
    
    return nodes, edges, parameters
