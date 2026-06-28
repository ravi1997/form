class ConditionEvaluator:
    @staticmethod
    def evaluate_condition(condition, variables):
        """
        Evaluates a single condition rule:
        condition: {"field": "q_id", "operator": "==" | "!=" | ">" | ">=" | "<" | "<=" | "contains", "value": val}
        """
        field = condition.get("field")
        op = condition.get("operator")
        target_value = condition.get("value")
        
        if field not in variables:
            return False
            
        actual_value = variables[field]
        
        try:
            if op == "==":
                return actual_value == target_value
            elif op == "!=":
                return actual_value != target_value
            elif op == ">":
                return float(actual_value) > float(target_value)
            elif op == ">=":
                return float(actual_value) >= float(target_value)
            elif op == "<":
                return float(actual_value) < float(target_value)
            elif op == "<=":
                return float(actual_value) <= float(target_value)
            elif op == "contains":
                if isinstance(actual_value, list):
                    return target_value in actual_value
                return str(target_value) in str(actual_value)
        except Exception:
            return False
        return False

    @classmethod
    def evaluate_rules(cls, rules, variables, logic_operator="AND"):
        """
        Evaluates a list of conditions joined by AND or OR logic operators.
        """
        if not rules:
            return True
            
        results = [cls.evaluate_condition(rule, variables) for rule in rules]
        
        if logic_operator.upper() == "OR":
            return any(results)
        return all(results)
