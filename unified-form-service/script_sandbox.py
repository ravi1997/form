class ScriptSandbox:
    @staticmethod
    def execute_script(script_body, answers):
        """
        Executes user-defined script inside a safe sandbox context.
        """
        locs = {"answers": answers, "is_ok": True, "err_msg": ""}
        globs = {"__builtins__": {
            "abs": abs,
            "min": min,
            "max": max,
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "list": list,
            "dict": dict,
            "set": set,
        }}
        try:
            exec(script_body, globs, locs)
            return locs.get("is_ok", True), locs.get("err_msg", "")
        except Exception as e:
            return False, str(e)
