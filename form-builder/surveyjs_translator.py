from lookup_resolver import LookupResolver

class SurveyJSTranslator:
    @staticmethod
    def map_condition_to_visible_if(rules, logic_operator="AND"):
        if not rules:
            return ""

        expressions = []
        for rule in rules:
            field = rule.get("field")
            op = rule.get("operator")
            val = rule.get("value")
            
            sjs_op = op
            if op == "==":
                sjs_op = "="
            elif op == "!=":
                sjs_op = "<>"

            if isinstance(val, str):
                formatted_val = f"'{val}'"
            else:
                formatted_val = str(val)

            if op == "contains":
                expressions.append(f"{{{field}}} contains {formatted_val}")
            else:
                expressions.append(f"{{{field}}} {sjs_op} {formatted_val}")

        joiner = " and " if logic_operator.upper() == "AND" else " or "
        return joiner.join(expressions)

    @classmethod
    def translate_question(cls, q, db=None, org_id=None):
        q_id = q.get("id")
        q_type = q.get("type")
        title = q.get("title", "")
        required = q.get("required", False)
        hint = q.get("hint")
        properties = q.get("properties", {})
        conditions = q.get("conditions", [])
        logic_operator = q.get("logic_operator", "AND")
        validations = q.get("validations", [])

        sjs_q = {
            "name": q_id,
            "title": title,
            "isRequired": required
        }

        if hint:
            sjs_q["description"] = hint

        # --- UI LAYOUT & ALIGNMENT PARAMETERS ---
        if "width" in properties:
            sjs_q["width"] = properties["width"]
        if "start_with_new_line" in properties:
            sjs_q["startWithNewLine"] = properties["start_with_new_line"]
        if "css_classes" in properties:
            sjs_q["cssClasses"] = properties["css_classes"]
        elif "css_class" in properties:
            sjs_q["cssClasses"] = {"root": properties["css_class"]}

        if "title_location" in properties:
            sjs_q["titleLocation"] = properties["title_location"] # top, left, bottom, hidden
        if "alignment" in properties:
            sjs_q["alignment"] = properties["alignment"]

        if conditions:
            visible_if = cls.map_condition_to_visible_if(conditions, logic_operator)
            if visible_if:
                sjs_q["visibleIf"] = visible_if

        if validations:
            sjs_validators = []
            for val_rule in validations:
                v_type = val_rule.get("type")
                if v_type == "regex":
                    sjs_validators.append({
                        "type": "regex",
                        "regex": val_rule.get("pattern"),
                        "text": val_rule.get("error_message", "Invalid format.")
                    })
                elif v_type == "range":
                    sjs_validators.append({
                        "type": "numeric",
                        "minValue": val_rule.get("min"),
                        "maxValue": val_rule.get("max"),
                        "text": val_rule.get("error_message", "Value out of range.")
                    })
            if sjs_validators:
                sjs_q["validators"] = sjs_validators

        is_repeatable = q.get("repeatable", False)
        if is_repeatable and q_type not in ["matrix_dynamic"]:
            wrapped_q = dict(sjs_q)
            wrapped_q["isRequired"] = True
            
            inner_q = cls.translate_base_question(q_type, properties, wrapped_q, db, org_id)
            inner_q["name"] = "value"
            inner_q["title"] = title
            
            sjs_q = {
                "type": "paneldynamic",
                "name": q_id,
                "title": title,
                "templateElements": [inner_q],
                "panelCount": properties.get("min_items", 1),
                "minPanelCount": properties.get("min_items", 1),
                "maxPanelCount": properties.get("max_items", 10),
                "panelAddText": properties.get("add_text", "Add Item"),
                "panelRemoveText": properties.get("remove_text", "Remove")
            }
            if hint:
                sjs_q["description"] = hint
            return sjs_q

        return cls.translate_base_question(q_type, properties, sjs_q, db, org_id)

    @classmethod
    def translate_base_question(cls, q_type, properties, sjs_q, db=None, org_id=None):
        if q_type in ["multiple_choice", "dropdown"]:
            is_multiselect = properties.get("multiselect", False)
            sjs_q["type"] = "checkbox" if (is_multiselect and q_type == "multiple_choice") else ("dropdown" if q_type == "dropdown" else "radiogroup")
            
            lookup_config = properties.get("lookup")
            if lookup_config and db is not None and org_id is not None:
                choices = LookupResolver.resolve_lookup_choices(db, lookup_config, org_id)
            else:
                choices = []
                for choice in properties.get("choices", []):
                    if isinstance(choice, dict):
                        choices.append({"value": choice.get("value"), "text": choice.get("value")})
                    else:
                        choices.append(str(choice))
            sjs_q["choices"] = choices

        elif q_type == "text":
            is_multiline = properties.get("multiline", False)
            sjs_q["type"] = "comment" if is_multiline else "text"
            if "placeholder" in properties:
                sjs_q["placeholder"] = properties["placeholder"]

        elif q_type in ["email", "url", "tel", "password"]:
            sjs_q["type"] = "text"
            sjs_q["inputType"] = q_type

        elif q_type == "number":
            sjs_q["type"] = "text"
            sjs_q["inputType"] = "number"
            if "min" in properties:
                sjs_q["min"] = properties["min"]
            if "max" in properties:
                sjs_q["max"] = properties["max"]

        elif q_type == "date":
            sjs_q["type"] = "text"
            sjs_q["inputType"] = properties.get("subtype", "date")

        elif q_type == "range":
            sjs_q["type"] = "rating"
            sjs_q["rateMin"] = properties.get("min", 1)
            sjs_q["rateMax"] = properties.get("max", 10)
            sjs_q["rateStep"] = properties.get("step", 1)

        elif q_type in ["file", "image", "camera", "signature"]:
            sjs_q["type"] = "signaturepad" if q_type == "signature" else "file"
            if q_type == "image":
                sjs_q["acceptedTypes"] = "image/*"
            elif q_type == "camera":
                sjs_q["acceptedTypes"] = "image/*"
                sjs_q["sourceType"] = "camera"

        elif q_type == "calculation":
            sjs_q["type"] = "expression"
            sjs_q["expression"] = sjs_q.get("expression", "")

        elif q_type == "boolean":
            sjs_q["type"] = "boolean"
            sjs_q["label"] = properties.get("label", sjs_q.get("title", ""))

        elif q_type == "ranking":
            sjs_q["type"] = "ranking"
            choices = []
            for choice in properties.get("choices", []):
                if isinstance(choice, dict):
                    choices.append({"value": choice.get("value"), "text": choice.get("value")})
                else:
                    choices.append(str(choice))
            sjs_q["choices"] = choices

        elif q_type == "matrix":
            sjs_q["type"] = "matrix"
            sjs_q["rows"] = properties.get("rows", [])
            sjs_q["columns"] = properties.get("columns", [])

        elif q_type == "matrix_dynamic":
            sjs_q["type"] = "matrixdynamic"
            columns = []
            for col in properties.get("columns", []):
                columns.append({
                    "name": col.get("id"),
                    "title": col.get("title", ""),
                    "cellType": col.get("type", "text")
                })
            sjs_q["columns"] = columns
            sjs_q["rowCount"] = properties.get("min_rows", 1)

        elif q_type in ["hint", "html"]:
            sjs_q["type"] = "html"
            sjs_q["html"] = properties.get("html_content", f"<div class='form-hint'>{sjs_q.get('description', '')}</div>")

        elif q_type == "image_picker":
            sjs_q["type"] = "imagepicker"
            choices = []
            for choice in properties.get("choices", []):
                choices.append({
                    "value": choice.get("value"),
                    "imageLink": choice.get("image_link")
                })
            sjs_q["choices"] = choices

        elif q_type == "multiple_text":
            sjs_q["type"] = "multipletext"
            items = []
            for item in properties.get("items", []):
                items.append({
                    "name": item.get("id"),
                    "title": item.get("title", "")
                })
            sjs_q["items"] = items

        elif q_type in ["barcode", "location", "rich_text"]:
            sjs_q["type"] = f"custom-{q_type}"
            for k, v in properties.items():
                sjs_q[k] = v

        elif q_type == "custom":
            sjs_q["type"] = properties.get("custom_widget_name", "text")
            for k, v in properties.items():
                if k not in ["custom_widget_name"]:
                    sjs_q[k] = v

        return sjs_q

    @classmethod
    def translate_form(cls, form_data, theme_data=None, db=None, org_id=None):
        active_version = None
        versions = form_data.get("versions", [])
        current_version_num = form_data.get("current_version", 1)

        for v in versions:
            if v.get("version_number") == current_version_num:
                active_version = v
                break
        
        if not active_version:
            if "sections" in form_data:
                active_version = form_data
            else:
                active_version = {
                    "sections": [{
                        "id": "default_section",
                        "title": "General",
                        "questions": form_data.get("questions", [])
                    }]
                }

        pages = []
        for sec in active_version.get("sections", []):
            is_repeatable_sec = sec.get("repeatable", False)
            elements = []
            
            if is_repeatable_sec:
                sec_questions = [cls.translate_question(q, db, org_id) for q in sec.get("questions", [])]
                panel_node = {
                    "type": "paneldynamic",
                    "name": sec.get("id", "section_panel"),
                    "title": sec.get("title", ""),
                    "templateElements": sec_questions,
                    "panelCount": sec.get("min_items", 1),
                    "minPanelCount": sec.get("min_items", 1),
                    "maxPanelCount": sec.get("max_items", 10),
                    "panelAddText": sec.get("add_text", "Add Section"),
                    "panelRemoveText": sec.get("remove_text", "Remove")
                }
                elements.append(panel_node)
            else:
                elements = [cls.translate_question(q, db, org_id) for q in sec.get("questions", [])]

            page_node = {
                "name": sec.get("id", "section"),
                "title": sec.get("title", ""),
                "description": sec.get("description", ""),
                "elements": elements
            }
            
            if "css_classes" in sec:
                page_node["cssClasses"] = sec["css_classes"]
            
            sec_conditions = sec.get("conditions", [])
            sec_logic_op = sec.get("logic_operator", "AND")
            if sec_conditions:
                visible_if = cls.map_condition_to_visible_if(sec_conditions, sec_logic_op)
                if visible_if:
                    page_node["visibleIf"] = visible_if

            pages.append(page_node)
        
        survey_json = {
            "title": form_data.get("title", ""),
            "description": form_data.get("description", ""),
            "pages": pages
        }

        # Apply Global styling overrides
        if theme_data and "style" in theme_data:
            style = theme_data["style"]
            survey_json["themeVariables"] = {
                "--sjs-font-family": style.get("font_family"),
                "--sjs-primary-background": style.get("primary_color"),
                "--sjs-general-backcolor": style.get("surface_color"),
                "--sjs-general-forecolor": style.get("text_color"),
                "--sjs-border-radius": style.get("border_radius"),
                "--sjs-shadow-depth": style.get("shadow_depth"),
                "--sjs-font-size": style.get("font_size"),
                "--sjs-input-backcolor": style.get("input_backcolor"),
                "--sjs-input-bordercolor": style.get("input_bordercolor")
            }
            # Custom stylesheets, navigation rules, and visual properties
            if "custom_css" in style:
                survey_json["customCss"] = style["custom_css"]
            if "show_navigation_buttons" in style:
                survey_json["showNavigationButtons"] = style["show_navigation_buttons"]
            if "show_progress_bar" in style:
                survey_json["showProgressBar"] = style["show_progress_bar"]
            if "title_alignment" in style:
                survey_json["titleAlignment"] = style["title_alignment"]

        return survey_json

