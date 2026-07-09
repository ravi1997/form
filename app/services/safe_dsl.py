from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class DSLValidationError(ValueError):
    pass


@dataclass
class Token:
    kind: str
    value: str


class DSLTokenizer:
    """Simple tokenizer for condition expressions."""

    OPERATORS = {
        ">=",
        "<=",
        "==",
        "!=",
        ">",
        "<",
        "+",
        "-",
        "*",
        "/",
        "(",
        ")",
        ",",
        "[",
        "]",
    }

    def tokenize(self, text: str) -> List[Token]:
        tokens: List[Token] = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch.isspace():
                i += 1
                continue

            if i + 1 < len(text) and text[i : i + 2] in {">=", "<=", "==", "!="}:
                tokens.append(Token("op", text[i : i + 2]))
                i += 2
                continue

            if ch in self.OPERATORS:
                tokens.append(Token("op", ch))
                i += 1
                continue

            if ch in {'"', "'"}:
                quote = ch
                i += 1
                start = i
                while i < len(text) and text[i] != quote:
                    if text[i] == "\\":
                        i += 2
                    else:
                        i += 1
                if i >= len(text):
                    raise DSLValidationError("Unterminated string literal")
                tokens.append(Token("string", text[start:i]))
                i += 1
                continue

            if ch.isdigit() or (
                ch == "." and i + 1 < len(text) and text[i + 1].isdigit()
            ):
                start = i
                i += 1
                while i < len(text) and (text[i].isdigit() or text[i] == "."):
                    i += 1
                tokens.append(Token("number", text[start:i]))
                continue

            if ch.isalpha() or ch == "_":
                start = i
                i += 1
                while i < len(text) and (text[i].isalnum() or text[i] in "_.$"):
                    i += 1
                word = text[start:i]
                kind = (
                    "keyword"
                    if word.upper()
                    in {"AND", "OR", "NOT", "IN", "TRUE", "FALSE", "NULL"}
                    else "ident"
                )
                tokens.append(Token(kind, word))
                continue

            raise DSLValidationError(f"Unexpected character: {ch}")

        return tokens


class DSLParser:
    """Recursive descent parser with safe AST output."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def parse(self) -> Dict[str, Any]:
        node = self._parse_or()
        if self.pos != len(self.tokens):
            raise DSLValidationError("Unexpected trailing tokens")
        return node

    def _peek(self) -> Optional[Token]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def _consume(self) -> Token:
        tok = self._peek()
        if tok is None:
            raise DSLValidationError("Unexpected end of expression")
        self.pos += 1
        return tok

    def _match_keyword(self, name: str) -> bool:
        tok = self._peek()
        if tok and tok.kind == "keyword" and tok.value.upper() == name:
            self.pos += 1
            return True
        return False

    def _match_op(self, op: str) -> bool:
        tok = self._peek()
        if tok and tok.kind == "op" and tok.value == op:
            self.pos += 1
            return True
        return False

    def _parse_or(self) -> Dict[str, Any]:
        node = self._parse_and()
        while self._match_keyword("OR"):
            right = self._parse_and()
            node = {"type": "logical", "op": "OR", "left": node, "right": right}
        return node

    def _parse_and(self) -> Dict[str, Any]:
        node = self._parse_not()
        while self._match_keyword("AND"):
            right = self._parse_not()
            node = {"type": "logical", "op": "AND", "left": node, "right": right}
        return node

    def _parse_not(self) -> Dict[str, Any]:
        if self._match_keyword("NOT"):
            return {"type": "not", "expr": self._parse_not()}
        return self._parse_comparison()

    def _parse_comparison(self) -> Dict[str, Any]:
        left = self._parse_expr()
        tok = self._peek()
        if tok and (
            (tok.kind == "op" and tok.value in {"==", "!=", ">", "<", ">=", "<="})
            or (tok.kind == "keyword" and tok.value.upper() == "IN")
        ):
            op = self._consume().value.upper()
            right = self._parse_expr()
            return {"type": "compare", "op": op, "left": left, "right": right}
        return left

    def _parse_expr(self) -> Dict[str, Any]:
        node = self._parse_term()
        while True:
            if self._match_op("+"):
                node = {
                    "type": "binary",
                    "op": "+",
                    "left": node,
                    "right": self._parse_term(),
                }
            elif self._match_op("-"):
                node = {
                    "type": "binary",
                    "op": "-",
                    "left": node,
                    "right": self._parse_term(),
                }
            else:
                break
        return node

    def _parse_term(self) -> Dict[str, Any]:
        node = self._parse_factor()
        while True:
            if self._match_op("*"):
                node = {
                    "type": "binary",
                    "op": "*",
                    "left": node,
                    "right": self._parse_factor(),
                }
            elif self._match_op("/"):
                node = {
                    "type": "binary",
                    "op": "/",
                    "left": node,
                    "right": self._parse_factor(),
                }
            else:
                break
        return node

    def _parse_factor(self) -> Dict[str, Any]:
        tok = self._peek()
        if tok is None:
            raise DSLValidationError("Unexpected end of expression")

        if self._match_op("("):
            expr = self._parse_or()
            if not self._match_op(")"):
                raise DSLValidationError("Missing closing parenthesis")
            return expr

        if self._match_op("["):
            values = []
            if not self._match_op("]"):
                values.append(self._parse_or())
                while self._match_op(","):
                    values.append(self._parse_or())
                if not self._match_op("]"):
                    raise DSLValidationError("Missing closing bracket")
            return {"type": "list", "items": values}

        tok = self._consume()
        if tok.kind == "number":
            return {
                "type": "literal",
                "value": float(tok.value) if "." in tok.value else int(tok.value),
            }
        if tok.kind == "string":
            return {"type": "literal", "value": tok.value}
        if tok.kind == "keyword":
            keyword = tok.value.upper()
            if keyword == "TRUE":
                return {"type": "literal", "value": True}
            if keyword == "FALSE":
                return {"type": "literal", "value": False}
            if keyword == "NULL":
                return {"type": "literal", "value": None}
            raise DSLValidationError(f"Unexpected keyword {tok.value}")

        if tok.kind in {"ident"}:
            if self._match_op("("):
                args = []
                if not self._match_op(")"):
                    args.append(self._parse_or())
                    while self._match_op(","):
                        args.append(self._parse_or())
                    if not self._match_op(")"):
                        raise DSLValidationError("Missing closing function parenthesis")
                return {"type": "call", "name": tok.value, "args": args}
            return {"type": "identifier", "name": tok.value}

        raise DSLValidationError(f"Unexpected token {tok}")


class DSLValidator:
    ALLOWED_FUNCTIONS = {
        "sum",
        "average",
        "min",
        "max",
        "count",
        "percentage",
        "weighted",
    }

    def validate(self, node: Dict[str, Any]) -> None:
        self._walk(node)

    def _walk(self, node: Dict[str, Any]) -> None:
        node_type = node.get("type")
        if node_type == "identifier":
            name = str(node.get("name", ""))
            if not self._is_safe_identifier_path(name):
                raise DSLValidationError(f"Identifier path '{name}' is not allowed")
            return
        if node_type == "call":
            name = str(node.get("name", "")).lower()
            if name not in self.ALLOWED_FUNCTIONS:
                raise DSLValidationError(f"Function '{name}' is not allowed")
            for arg in node.get("args", []):
                self._walk(arg)
            return

        for key in ("left", "right", "expr"):
            child = node.get(key)
            if isinstance(child, dict):
                self._walk(child)

        for item in node.get("items", []):
            if isinstance(item, dict):
                self._walk(item)

    @staticmethod
    def _is_safe_identifier_path(name: str) -> bool:
        if not name or "__" in name:
            return False
        parts = name.split(".")
        return all(part and part.replace("_", "").isalnum() for part in parts)


class DSLEvaluator:
    def __init__(self, context: Dict[str, Any]):
        self.context = context

    def evaluate(self, node: Dict[str, Any]) -> Any:
        t = node.get("type")
        if t == "literal":
            return node.get("value")
        if t == "identifier":
            return self._resolve_field(node["name"])
        if t == "list":
            return [self.evaluate(item) for item in node.get("items", [])]
        if t == "binary":
            left = self.evaluate(node["left"])
            right = self.evaluate(node["right"])
            op = node["op"]
            if op == "+":
                return (left or 0) + (right or 0)
            if op == "-":
                return (left or 0) - (right or 0)
            if op == "*":
                return (left or 0) * (right or 0)
            if op == "/":
                return (left or 0) / (right or 1)
        if t == "compare":
            left = self.evaluate(node["left"])
            right = self.evaluate(node["right"])
            op = node["op"]
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if op == ">":
                return left > right
            if op == "<":
                return left < right
            if op == ">=":
                return left >= right
            if op == "<=":
                return left <= right
            if op == "IN":
                return left in (right or [])
        if t == "logical":
            left = bool(self.evaluate(node["left"]))
            if node["op"] == "AND":
                return left and bool(self.evaluate(node["right"]))
            return left or bool(self.evaluate(node["right"]))
        if t == "not":
            return not bool(self.evaluate(node["expr"]))
        if t == "call":
            fn = node["name"].lower()
            args = [self.evaluate(a) for a in node.get("args", [])]
            return self._eval_function(fn, args)

        raise DSLValidationError(f"Unsupported AST node: {t}")

    def _resolve_field(self, path: str) -> Any:
        if not DSLValidator._is_safe_identifier_path(path):
            raise DSLValidationError(f"Identifier path '{path}' is not allowed")
        value: Any = self.context
        for part in path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value

    def _eval_function(self, fn: str, args: List[Any]) -> Any:
        values = args[0] if args and isinstance(args[0], list) else args
        nums = [
            float(v)
            for v in values
            if isinstance(v, (int, float))
            or (isinstance(v, str) and v.replace(".", "", 1).isdigit())
        ]

        if fn == "sum":
            return sum(nums)
        if fn == "average":
            return sum(nums) / len(nums) if nums else 0
        if fn == "min":
            return min(nums) if nums else 0
        if fn == "max":
            return max(nums) if nums else 0
        if fn == "count":
            return len(values)
        if fn == "percentage":
            if len(args) < 2:
                return 0
            numerator = float(args[0] or 0)
            denominator = float(args[1] or 0)
            return (numerator / denominator * 100) if denominator else 0
        if fn == "weighted":
            if (
                len(args) != 2
                or not isinstance(args[0], list)
                or not isinstance(args[1], list)
            ):
                return 0
            vals = [float(v) for v in args[0]]
            weights = [float(w) for w in args[1]]
            if not vals or not weights or len(vals) != len(weights):
                return 0
            total_weight = sum(weights)
            return (
                sum(v * w for v, w in zip(vals, weights)) / total_weight
                if total_weight
                else 0
            )
        raise DSLValidationError(f"Unsupported function: {fn}")


def parse_and_validate_expression(expression: str) -> Dict[str, Any]:
    tokens = DSLTokenizer().tokenize(expression)
    ast = DSLParser(tokens).parse()
    DSLValidator().validate(ast)
    return ast


def evaluate_expression(expression: str, context: Dict[str, Any]) -> Any:
    ast = parse_and_validate_expression(expression)
    return DSLEvaluator(context).evaluate(ast)
