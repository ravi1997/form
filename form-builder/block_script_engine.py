import logging
from condition_evaluator import ConditionEvaluator

logger = logging.getLogger("BlockScriptEngine")

class BlockScriptEngine:
    @classmethod
    def evaluate_block_script(cls, block_config, submission_answers, db=None, form_id=None, project_id=None, org_id=None):
        """
        Executes block-based logical structures.
        Supports scopes:
        - questions: direct lookup in submission_answers
        - sections: checking visibility / repeatable data
        - forms & projects: database context queries
        """
        errors = {}
        mutated_answers = dict(submission_answers)

        blocks = block_config.get("blocks", [])
        
        # Build execution scopes
        scopes = {
            "questions": mutated_answers,
            "form_id": form_id,
            "project_id": project_id,
            "org_id": org_id,
            "db": db
        }

        for block in blocks:
            b_type = block.get("type")
            
            if b_type == "conditional":
                # IF condition THEN execute actions
                condition = block.get("condition", {})
                then_actions = block.get("then_actions", [])
                else_actions = block.get("else_actions", [])
                
                # Evaluate condition using ConditionEvaluator
                is_met = ConditionEvaluator.evaluate_condition(condition, mutated_answers)
                actions_to_run = then_actions if is_met else else_actions
                
                cls._run_actions(actions_to_run, mutated_answers, errors, scopes)

            elif b_type == "set_value":
                cls._execute_set_value(block, mutated_answers, scopes)

            elif b_type == "validation_rule":
                cls._execute_validation_rule(block, mutated_answers, errors, scopes)

        return mutated_answers, errors

    @classmethod
    def _run_actions(cls, actions, answers, errors, scopes):
        for action in actions:
            act_type = action.get("type")
            if act_type == "show_error":
                field_id = action.get("field_id")
                message = action.get("message", "Validation failed.")
                errors[field_id] = message
            elif act_type == "set_value":
                cls._execute_set_value(action, answers, scopes)

    @classmethod
    def _execute_set_value(cls, block, answers, scopes):
        target_field = block.get("field_id")
        value = block.get("value")
        
        # Handle dynamic cross-form lookup values if value is a query config
        if isinstance(value, dict) and value.get("source") == "cross_form_lookup":
            # Lookup answers in other forms of the same project
            db = scopes.get("db")
            project_id = scopes.get("project_id")
            source_form_id = value.get("form_id")
            source_field = value.get("field_id")
            
            if db and project_id and source_form_id and source_field:
                try:
                    # Query latest response submitted in the project for source_form_id
                    from bson import ObjectId
                    latest_resp = db["responses"].find_one(
                        {
                            "form_id": ObjectId(source_form_id),
                            "project_id": ObjectId(project_id) if isinstance(project_id, str) else project_id
                        },
                        sort=[("submitted_at", -1)]
                    )
                    if latest_resp and "answers" in latest_resp:
                        answers[target_field] = latest_resp["answers"].get(source_field)
                except Exception as e:
                    logger.error(f"Set value lookup failed: {str(e)}")
        else:
            answers[target_field] = value

    @classmethod
    def _execute_validation_rule(cls, block, answers, errors, scopes):
        field_id = block.get("field_id")
        rule = block.get("rule", {})
        error_message = block.get("error_message", "Rule validation failed.")
        
        # Evaluate condition logic
        if not ConditionEvaluator.evaluate_condition(rule, answers):
            errors[field_id] = error_message

    @classmethod
    def detect_cycles(cls, block_config):
        """
        Detects circular dependencies in block script configuration.
        Returns a list of field IDs involved in the cycle if one is found, else None.
        """
        if not block_config:
            return None
        blocks = block_config.get("blocks", [])
        adj = {}
        
        def get_referenced_fields(cond):
            fields = []
            if not cond:
                return fields
            if "field" in cond:
                fields.append(cond["field"])
            for rule in cond.get("rules", []):
                fields.extend(get_referenced_fields(rule))
            return fields

        for block in blocks:
            b_type = block.get("type")
            if b_type == "conditional":
                cond = block.get("condition", {})
                ref_fields = get_referenced_fields(cond)
                for action in block.get("then_actions", []) + block.get("else_actions", []):
                    if action.get("type") == "set_value":
                        target = action.get("field_id")
                        if target:
                            for rf in ref_fields:
                                if rf not in adj:
                                    adj[rf] = []
                                adj[rf].append(target)
            elif b_type == "set_value":
                target = block.get("field_id")
                val = block.get("value")
                if isinstance(val, dict) and val.get("source") == "formula":
                    import ast
                    try:
                        expr = val.get("expression", "")
                        tree = ast.parse(expr, mode='eval')
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Name):
                                if node.id not in adj:
                                    adj[node.id] = []
                                adj[node.id].append(target)
                    except Exception:
                        pass
                        
        visited = {}
        cycle_path = []
        
        def dfs(node):
            visited[node] = 1
            cycle_path.append(node)
            for neighbor in adj.get(node, []):
                if visited.get(neighbor) == 1:
                    idx = cycle_path.index(neighbor)
                    return cycle_path[idx:]
                if visited.get(neighbor) != 2:
                    res = dfs(neighbor)
                    if res:
                        return res
            cycle_path.pop()
            visited[node] = 2
            return None

        for n in list(adj.keys()):
            if visited.get(n) != 2:
                cycle = dfs(n)
                if cycle:
                    return cycle
        return None
