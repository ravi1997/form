import ast
import operator
import re
from datetime import datetime
from condition_evaluator import ConditionEvaluator
from block_script_engine import BlockScriptEngine
from lookup_resolver import LookupResolver
from encryption_helper import EncryptionHelper
from auth import AuthManager

class SafeFormulaEvaluator:
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos
    }

    @classmethod
    def evaluate(cls, expression_str, variables):
        try:
            node = ast.parse(expression_str, mode='eval')
            return cls._eval_node(node.body, variables)
        except Exception as e:
            raise ValueError(f"Failed to evaluate formula '{expression_str}': {str(e)}")

    @classmethod
    def _eval_node(cls, node, variables):
        if isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise TypeError(f"Unallowed constant type: {type(node.value)}")
        elif isinstance(node, ast.Name):
            if node.id in variables:
                val = variables[node.id]
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return val
            raise NameError(f"Undefined variable in formula: {node.id}")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type in cls.operators:
                left = cls._eval_node(node.left, variables)
                right = cls._eval_node(node.right, variables)
                return cls.operators[op_type](left, right)
            raise TypeError(f"Unsupported binary operator: {op_type}")
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type in cls.operators:
                operand = cls._eval_node(node.operand, variables)
                return cls.operators[op_type](operand)
            raise TypeError(f"Unsupported unary operator: {op_type}")
        else:
            raise TypeError(f"Unsupported element in formula: {type(node)}")


class FormSubmissionValidator:
    def __init__(self, form_definition, version_number=None, is_draft=False, db=None, org_id=None, request_headers=None):
        self.form = form_definition
        self.errors = {}
        self.validated_answers = {}
        self.version_number = version_number or form_definition.get("current_version", 1)
        self.is_draft = is_draft
        self.db = db
        self.org_id = org_id
        self.headers = request_headers or {}

    def get_active_version(self):
        versions = self.form.get("versions", [])
        for v in versions:
            if v.get("version_number") == self.version_number:
                return v
        return None

    def get_active_sections(self):
        v = self.get_active_version()
        if v:
            return v.get("sections", [])
        if "sections" in self.form:
            return self.form.get("sections", [])
        return [{
            "id": "default_section",
            "title": "General",
            "questions": self.form.get("questions", [])
        }]

    def validate_and_compute(self, submitted_data):
        self.errors = {}
        self.validated_answers = {}

        # --- 1. Soft-Delete & Lifecycle States (Active, Paused, Archived) ---
        if self.form.get("deleted", False) or self.form.get("lifecycle") == "Archived":
            self.errors["form"] = "This form has been archived and no longer accepts submissions."
            return False, {}, self.errors

        if self.form.get("lifecycle") == "Paused":
            self.errors["form"] = "This form is currently paused and not accepting responses."
            return False, {}, self.errors

        # --- 2. Password Protection Check ---
        if self.form.get("password_protected", False) and not self.is_draft:
            submitted_pwd = self.headers.get("X-Form-Password")
            hashed_pwd = self.form.get("password_hash")
            if not submitted_pwd or not hashed_pwd or not AuthManager.verify_password(submitted_pwd, hashed_pwd):
                self.errors["form"] = "Access denied. Invalid or missing form password."
                return False, {}, self.errors

        # --- 3. Operational Time Access Windows ---
        access_window = self.form.get("access_window")
        if access_window and not self.is_draft:
            now = datetime.utcnow()
            # In Python, weekday is 0 (Monday) to 6 (Sunday)
            current_day = now.weekday()
            current_hour = now.hour
            
            allowed_days = access_window.get("days", [0, 1, 2, 3, 4, 5, 6])
            start_hour = access_window.get("start_hour", 0)
            end_hour = access_window.get("end_hour", 24)

            if current_day not in allowed_days or current_hour < start_hour or current_hour >= end_hour:
                self.errors["form"] = "This form is closed outside of standard operational access hours."
                return False, {}, self.errors

        # --- 4. Expiry Rules & Quota limit validation ---
        if not self.is_draft:
            start_date_str = self.form.get("start_date")
            end_date_str = self.form.get("end_date")
            now = datetime.utcnow()
            
            if start_date_str:
                try:
                    start_date = datetime.fromisoformat(start_date_str)
                    if now < start_date:
                        self.errors["form"] = "This form is not yet accepting responses."
                        return False, {}, self.errors
                except ValueError:
                    pass

            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str)
                    if now > end_date:
                        self.errors["form"] = "This form is closed and no longer accepting responses."
                        return False, {}, self.errors
                except ValueError:
                    pass

            max_submissions = self.form.get("max_submissions")
            if max_submissions is not None and self.db is not None:
                current_count = self.db["responses"].count_documents({
                    "form_id": self.form.get("_id"),
                    "status": "Submitted"
                })
                if current_count >= max_submissions:
                    self.errors["form"] = "The response quota for this form has been exceeded."
                    return False, {}, self.errors

        sections = self.get_active_sections()
        variables = {}

        temp_vars = {}
        for sec in sections:
            is_repeatable_sec = sec.get("repeatable", False)
            sec_id = sec.get("id")
            
            if is_repeatable_sec:
                raw_items = submitted_data.get(sec_id, [])
                if isinstance(raw_items, list):
                    temp_vars[sec_id] = raw_items
            else:
                for q in sec.get("questions", []):
                    q_id = q.get("id")
                    if q_id in submitted_data:
                        val = submitted_data[q_id]
                        temp_vars[q_id] = val
                        if q.get("type") == "multiple_choice":
                            choices = q.get("properties", {}).get("choices", [])
                            for c in choices:
                                if isinstance(c, dict) and c.get("value") == val:
                                    temp_vars[f"{q_id}_score"] = c.get("score")
                                    break

        calc_questions = []
        sensitive_fields = []

        for sec in sections:
            sec_id = sec.get("id")
            is_repeatable_sec = sec.get("repeatable", False)
            
            sec_conditions = sec.get("conditions", [])
            sec_logic_op = sec.get("logic_operator", "AND")
            if sec_conditions:
                if not ConditionEvaluator.evaluate_rules(sec_conditions, temp_vars, sec_logic_op):
                    continue

            if is_repeatable_sec:
                sec_entries = submitted_data.get(sec_id)
                if not sec_entries:
                    if sec.get("required", False) and not self.is_draft:
                        self.errors[sec_id] = "Section entries are required."
                    continue

                if not isinstance(sec_entries, list):
                    self.errors[sec_id] = "Section answers must be an array of objects."
                    continue

                validated_list = []
                for entry_idx, entry_dict in enumerate(sec_entries):
                    if not isinstance(entry_dict, dict):
                        self.errors[f"{sec_id}[{entry_idx}]"] = "Entry must be a dictionary."
                        continue
                    
                    sub_form = {"questions": sec.get("questions", [])}
                    sub_validator = FormSubmissionValidator(
                        sub_form, 
                        is_draft=self.is_draft, 
                        db=self.db, 
                        org_id=self.org_id,
                        request_headers=self.headers
                    )
                    is_ok, sub_answers, sub_errors = sub_validator.validate_and_compute(entry_dict)
                    
                    if not is_ok:
                        for k, err in sub_errors.items():
                            self.errors[f"{sec_id}[{entry_idx}].{k}"] = err
                    else:
                        validated_list.append(sub_answers)
                
                self.validated_answers[sec_id] = validated_list
                variables[sec_id] = len(validated_list)

            else:
                for q in sec.get("questions", []):
                    q_id = q.get("id")
                    q_type = q.get("type")
                    required = q.get("required", False)
                    properties = q.get("properties", {})
                    q_conditions = q.get("conditions", [])
                    q_logic_op = q.get("logic_operator", "AND")

                    if properties.get("sensitive", False):
                        sensitive_fields.append(q_id)

                    if q_conditions:
                        if not ConditionEvaluator.evaluate_rules(q_conditions, temp_vars, q_logic_op):
                            continue

                    if q_type in ["calculation", "html"]:
                        if q_type == "calculation":
                            calc_questions.append(q)
                        continue

                    val = submitted_data.get(q_id)
                    if val is None or val == "":
                        if required and not self.is_draft:
                            self.errors[q_id] = "This field is required."
                        continue

                    is_repeatable_q = q.get("repeatable", False)
                    if is_repeatable_q and q_type not in ["matrix_dynamic"]:
                        if not isinstance(val, list):
                            self.errors[q_id] = "Value must be an array of repeated question entries."
                            continue
                        
                        validated_items = []
                        q_errs = []
                        for idx, item in enumerate(val):
                            is_ok, item_val, err = self.validate_field_value(q_type, item, properties, q.get("validations", []))
                            if not is_ok:
                                q_errs.append(f"Index [{idx}]: {err}")
                            else:
                                validated_items.append(item_val)
                        
                        if q_errs and not self.is_draft:
                            self.errors[q_id] = " | ".join(q_errs)
                        else:
                            self.validated_answers[q_id] = validated_items
                            variables[q_id] = len(validated_items)
                    else:
                        is_ok, final_val, err = self.validate_field_value(q_type, val, properties, q.get("validations", []))
                        if not is_ok:
                            if not self.is_draft:
                                self.errors[q_id] = err
                        else:
                            self.validated_answers[q_id] = final_val
                            if q_type in ["multiple_choice", "dropdown", "image_picker"] and not isinstance(final_val, list):
                                choices = properties.get("choices", [])
                                score_mapped = False
                                for c in choices:
                                    if isinstance(c, dict) and c.get("value") == final_val:
                                        variables[f"{q_id}_score"] = c.get("score")
                                        variables[q_id] = c.get("score")
                                        score_mapped = True
                                        break
                                if not score_mapped:
                                    variables[q_id] = final_val
                            else:
                                variables[q_id] = final_val

        # 5. Evaluate formulas
        for q in calc_questions:
            q_id = q.get("id")
            formula = q.get("calculation_formula")
            if not formula:
                continue
            try:
                result = SafeFormulaEvaluator.evaluate(formula, variables)
                self.validated_answers[q_id] = result
                variables[q_id] = result
            except Exception as e:
                self.errors[q_id] = f"Formula evaluation error: {str(e)}"

        # 6. Run Building-Block Visual Scripting Engine
        active_ver = self.get_active_version()
        block_script = None
        if active_ver and active_ver.get("block_script"):
            block_script = active_ver["block_script"]
        elif self.form.get("block_script"):
            block_script = self.form["block_script"]

        if block_script and not self.is_draft:
            mutated, block_errors = BlockScriptEngine.evaluate_block_script(
                block_script, 
                self.validated_answers,
                db=self.db,
                form_id=self.form.get("_id"),
                project_id=self.form.get("project_id"),
                org_id=self.org_id
            )
            self.validated_answers.update(mutated)
            self.errors.update(block_errors)

        # 7. Apply Encryption on Sensitive Fields (PII)
        if sensitive_fields and not self.is_draft:
            self.validated_answers = EncryptionHelper.process_sensitive_fields(
                self.validated_answers,
                sensitive_fields,
                action="encrypt"
            )

        is_valid = len(self.errors) == 0
        return is_valid, self.validated_answers, self.errors

    def validate_field_value(self, q_type, val, properties, validations):
        if q_type in ["multiple_choice", "dropdown", "image_picker"]:
            lookup_config = properties.get("lookup")
            if lookup_config and self.db is not None and self.org_id is not None:
                choices = LookupResolver.resolve_lookup_choices(self.db, lookup_config, self.org_id)
                allowed_values = [c.get("value") for c in choices]
            else:
                choices = properties.get("choices", [])
                allowed_values = []
                for c in choices:
                    if isinstance(c, dict):
                        allowed_values.append(c.get("value"))
                    else:
                        allowed_values.append(str(c))

            is_multiselect = properties.get("multiselect", False)
            if is_multiselect:
                if not isinstance(val, list):
                    return False, None, "Value must be a list."
                invalid = [v for v in val if v not in allowed_values]
                if invalid:
                    return False, None, f"Invalid selections: {', '.join(map(str, invalid))}."
                return True, val, None
            else:
                if val not in allowed_values:
                    return False, None, f"Value '{val}' is not a valid choice."
                return True, val, None

        elif q_type in ["text", "password", "barcode", "rich_text"]:
            if not isinstance(val, str):
                return False, None, "Value must be a string."
            min_len = properties.get("min_length")
            max_len = properties.get("max_length")
            if min_len is not None and len(val) < min_len:
                return False, None, f"Text length must be at least {min_len} characters."
            if max_len is not None and len(val) > max_len:
                return False, None, f"Text length must not exceed {max_len} characters."
            
            for rule in validations:
                if rule.get("type") == "regex":
                    pattern = rule.get("pattern")
                    if pattern and not re.match(pattern, val):
                        return False, None, rule.get("error_message", "Format is invalid.")
            return True, val, None

        elif q_type == "email":
            if not isinstance(val, str):
                return False, None, "Value must be a string email."
            email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
            if not re.match(email_pattern, val):
                return False, None, "Email address is invalid."
            return True, val, None

        elif q_type == "url":
            if not isinstance(val, str):
                return False, None, "Value must be a URL string."
            if not (val.startswith("http://") or val.startswith("https://")):
                return False, None, "URL must start with http:// or https://."
            return True, val, None

        elif q_type == "tel":
            if not isinstance(val, str):
                return False, None, "Value must be a phone number string."
            tel_pattern = r"^\+?[0-9\s\-()]{7,20}$"
            if not re.match(tel_pattern, val):
                return False, None, "Telephone number format is invalid."
            return True, val, None

        elif q_type == "number":
            try:
                num_val = float(val)
                if num_val.is_integer():
                    num_val = int(num_val)
            except (ValueError, TypeError):
                return False, None, "Value must be a number."
            
            min_val = properties.get("min")
            max_val = properties.get("max")
            if min_val is not None and num_val < min_val:
                return False, None, f"Value must be at least {min_val}."
            if max_val is not None and num_val > max_val:
                return False, None, f"Value must not exceed {max_val}."
            return True, num_val, None

        elif q_type == "date":
            try:
                if "T" in str(val):
                    datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                else:
                    datetime.strptime(str(val), "%Y-%m-%d")
            except ValueError:
                return False, None, "Value must be a valid date format."
            return True, val, None

        elif q_type == "range":
            try:
                num_val = int(val)
            except (ValueError, TypeError):
                return False, None, "Value must be an integer."
            
            min_val = properties.get("min", 1)
            max_val = properties.get("max", 10)
            if num_val < min_val or num_val > max_val:
                return False, None, f"Value must be between {min_val} and {max_val}."
            return True, num_val, None

        elif q_type in ["file", "image", "camera", "signature"]:
            if not isinstance(val, str):
                return False, None, "Value must be a file reference path."
            return True, val, None

        elif q_type == "boolean":
            if not isinstance(val, bool):
                return False, None, "Value must be a boolean (true/false)."
            return True, val, None

        elif q_type == "ranking":
            choices = [c.get("value") if isinstance(c, dict) else str(c) for c in properties.get("choices", [])]
            if not isinstance(val, list):
                return False, None, "Value must be an ordered list of selections."
            invalid = [v for v in val if v not in choices]
            if invalid:
                return False, None, f"Invalid selections: {', '.join(map(str, invalid))}."
            if len(val) != len(set(val)):
                return False, None, "Ranking choices must be unique."
            return True, val, None

        elif q_type == "matrix":
            if not isinstance(val, dict):
                return False, None, "Matrix answer must be a key-value dictionary."
            rows = properties.get("rows", [])
            columns = properties.get("columns", [])
            for r_key, c_val in val.items():
                if r_key not in rows:
                    return False, None, f"Invalid matrix row: {r_key}"
                if c_val not in columns:
                    return False, None, f"Invalid matrix choice: {c_val}"
            return True, val, None

        elif q_type == "matrix_dynamic":
            if not isinstance(val, list):
                return False, None, "Dynamic Matrix must be a list of row dictionaries."
            columns_ids = [c.get("id") for c in properties.get("columns", [])]
            for idx, row in enumerate(val):
                if not isinstance(row, dict):
                    return False, None, f"Row index [{idx}] must be a dictionary."
                for c_id in row.keys():
                    if c_id not in columns_ids:
                        return False, None, f"Invalid dynamic matrix column: {c_id}"
            return True, val, None

        elif q_type == "multiple_text":
            if not isinstance(val, dict):
                return False, None, "Multiple Text answer must be a key-value dictionary."
            item_ids = [item.get("id") for item in properties.get("items", [])]
            for sub_key, sub_val in val.items():
                if sub_key not in item_ids:
                    return False, None, f"Invalid input field key: {sub_key}"
                if not isinstance(sub_val, str):
                    return False, None, f"Field value for '{sub_key}' must be a string."
            return True, val, None

        elif q_type == "location":
            if not isinstance(val, dict):
                return False, None, "Location must be a coordinate dictionary mapping latitude and longitude."
            if "latitude" not in val or "longitude" not in val:
                return False, None, "Location requires latitude and longitude fields."
            try:
                float(val["latitude"])
                float(val["longitude"])
            except (ValueError, TypeError):
                return False, None, "Coordinates must be numeric floating values."
            return True, val, None

        elif q_type == "custom":
            return True, val, None

        return False, None, f"Unsupported question type: {q_type}"
