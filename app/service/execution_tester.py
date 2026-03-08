import ast
import sys
import json
from io import StringIO
from typing import Dict, Any, List, Optional


# ---------------------------------------------------------------------------
# Parameter value parser
# ---------------------------------------------------------------------------

def _parse_param_value(value: Any) -> Any:
    """
    Try to intelligently convert a parameter value:
    - Numeric strings  → int / float
    - 'true'/'false'   → bool
    - JSON strings     → dict / list  (supports objects and arrays)
    - Everything else  → unchanged
    """
    if not isinstance(value, str):
        return value  # already a Python object (sent as JSON from frontend)

    stripped = value.strip()

    # JSON object or array
    if stripped and stripped[0] in ('{', '[', '"'):
        try:
            return json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            pass  # fall through to other conversions

    # Boolean literals
    if stripped.lower() == "true":
        return True
    if stripped.lower() == "false":
        return False

    # Numeric
    if stripped != "":
        try:
            int_val = int(stripped)
            return int_val
        except ValueError:
            pass
        try:
            float_val = float(stripped)
            return float_val
        except ValueError:
            pass

    return value


def _prepare_params(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Apply _parse_param_value to every parameter."""
    return {k: _parse_param_value(v) for k, v in parameters.items()}


# ---------------------------------------------------------------------------
# Code execution
# ---------------------------------------------------------------------------

def test_code_with_parameters(code: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the provided code with the given parameters and return the result.
    Parameters can be strings, numbers, booleans, JSON arrays, or JSON objects.
    """
    local_vars: Dict[str, Any] = _prepare_params(parameters)

    # Capture stdout
    old_stdout = sys.stdout
    captured_output = StringIO()
    sys.stdout = captured_output

    result: Dict[str, Any] = {
        "success": False,
        "stdout": "",
        "return_value": None,
        "error": None,
    }

    try:
        tree = ast.parse(code)

        # Find first function definition
        function_name: Optional[str] = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                function_name = node.name
                break

        # Execute the whole module so functions are defined
        exec(compile(tree, filename="<ast>", mode="exec"), {}, local_vars)

        if function_name and function_name in local_vars:
            func = local_vars[function_name]
            # Only pass params that the function actually accepts
            import inspect
            try:
                sig = inspect.signature(func)
                func_params = {
                    k: v for k, v in local_vars.items()
                    if k in sig.parameters
                }
            except (ValueError, TypeError):
                func_params = {k: v for k, v in parameters.items()}
            result["return_value"] = func(**func_params)
        elif "result" in local_vars:
            result["return_value"] = local_vars["result"]

        result["success"] = True

    except Exception as e:
        import traceback
        result["error"] = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
        }
    finally:
        sys.stdout = old_stdout
        result["stdout"] = captured_output.getvalue()

    return result


# ---------------------------------------------------------------------------
# Execution path tracer
# ---------------------------------------------------------------------------

def trace_execution_path(code: str, parameters: Dict[str, Any]) -> List[str]:
    """
    Trace the actual execution path of the code with the given parameters.
    Returns a list of line numbers (as strings) in execution order.
    Parameters can be strings, numbers, booleans, JSON arrays, or JSON objects.
    """
    execution_path: List[str] = []
    code_lines = code.splitlines()

    def trace_calls(frame, event, arg):
        if event == "line":
            lineno = frame.f_lineno
            if 0 < lineno <= len(code_lines):
                execution_path.append(str(lineno))
        return trace_calls

    local_vars: Dict[str, Any] = _prepare_params(parameters)

    tree = ast.parse(code)
    function_name: Optional[str] = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            function_name = node.name
            break

    sys.settrace(trace_calls)
    try:
        exec(code, {}, local_vars)

        if function_name and function_name in local_vars:
            func = local_vars[function_name]
            import inspect
            try:
                sig = inspect.signature(func)
                func_params = {
                    k: v for k, v in local_vars.items()
                    if k in sig.parameters
                }
            except (ValueError, TypeError):
                func_params = {k: v for k, v in parameters.items()}
            func(**func_params)
    except Exception:
        pass
    finally:
        sys.settrace(None)

    return execution_path