from __future__ import annotations

from dataclasses import dataclass
import ast
from datetime import datetime, timezone
from decimal import InvalidOperation
from decimal import Decimal
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence


class DSLExpressionError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


@dataclass(frozen=True)
class ASTNode:
    node_type: str
    value: Any = None
    left: Optional["ASTNode"] = None
    right: Optional["ASTNode"] = None
    args: Optional[List["ASTNode"]] = None


TOKEN_REGEX = re.compile(
    r"""
    (?P<SPACE>\s+)
    |(?P<NUMBER>\d+(?:\.\d+)?)
    |(?P<STRING>"([^"\\]|\\.)*"|'([^'\\]|\\.)*')
    |(?P<OP>==|!=|>=|<=|\+|-|\*|/|%|>|<)
    |(?P<LPAREN>\()
    |(?P<RPAREN>\))
    |(?P<LBRACK>\[)
    |(?P<RBRACK>\])
    |(?P<COMMA>,)
    |(?P<IDENT>[A-Za-z_][A-Za-z0-9_\.]*)
    """,
    re.VERBOSE,
)


KEYWORDS = {
    "AND",
    "OR",
    "NOT",
    "IN",
    "BETWEEN",
    "TRUE",
    "FALSE",
    "NULL",
}


class Tokenizer:
    def tokenize(self, source: str) -> List[Token]:
        if not source or not source.strip():
            raise DSLExpressionError("Expression cannot be empty")

        tokens: List[Token] = []
        position = 0
        while position < len(source):
            match = TOKEN_REGEX.match(source, position)
            if not match:
                raise DSLExpressionError(f"Unexpected token at position {position}")

            kind = match.lastgroup or ""
            raw = match.group(0)
            position = match.end()

            if kind == "SPACE":
                continue
            if kind == "IDENT" and raw.upper() in KEYWORDS:
                tokens.append(Token("KEYWORD", raw.upper(), match.start()))
                continue
            tokens.append(Token(kind, raw, match.start()))
        return tokens


class Parser:
    def __init__(self, tokens: Sequence[Token]):
        self.tokens = list(tokens)
        self.index = 0

    def parse(self) -> ASTNode:
        node = self._parse_or()
        token = self._peek()
        if token is not None:
            raise DSLExpressionError(
                f"Unexpected token {token.value!r} at position {token.position}"
            )
        return node

    def _peek(self) -> Optional[Token]:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def _consume(self) -> Token:
        token = self._peek()
        if token is None:
            raise DSLExpressionError("Unexpected end of expression")
        self.index += 1
        return token

    def _match(self, kind: str, value: Optional[str] = None) -> bool:
        token = self._peek()
        if token is None or token.kind != kind:
            return False
        if value is not None and token.value != value:
            return False
        self.index += 1
        return True

    def _match_keyword(self, keyword: str) -> bool:
        token = self._peek()
        if token is None or token.kind != "KEYWORD" or token.value != keyword:
            return False
        self.index += 1
        return True

    def _parse_or(self) -> ASTNode:
        node = self._parse_and()
        while self._match_keyword("OR"):
            node = ASTNode("binary", "OR", left=node, right=self._parse_and())
        return node

    def _parse_and(self) -> ASTNode:
        node = self._parse_not()
        while self._match_keyword("AND"):
            node = ASTNode("binary", "AND", left=node, right=self._parse_not())
        return node

    def _parse_not(self) -> ASTNode:
        if self._match_keyword("NOT"):
            return ASTNode("unary", "NOT", right=self._parse_not())
        return self._parse_comparison()

    def _parse_comparison(self) -> ASTNode:
        node = self._parse_additive()

        if self._match_keyword("BETWEEN"):
            lower = self._parse_additive()
            if not self._match_keyword("AND"):
                raise DSLExpressionError("BETWEEN requires AND")
            upper = self._parse_additive()
            return ASTNode("between", None, left=node, args=[lower, upper])

        if self._match_keyword("IN"):
            rhs = self._parse_additive()
            return ASTNode("binary", "IN", left=node, right=rhs)

        if self._match_keyword("NOT"):
            if not self._match_keyword("IN"):
                raise DSLExpressionError("Expected IN after NOT")
            rhs = self._parse_additive()
            return ASTNode("binary", "NOT_IN", left=node, right=rhs)

        token = self._peek()
        if (
            token
            and token.kind == "OP"
            and token.value in {"==", "!=", ">", "<", ">=", "<="}
        ):
            op = self._consume().value
            rhs = self._parse_additive()
            return ASTNode("binary", op, left=node, right=rhs)
        return node

    def _parse_additive(self) -> ASTNode:
        node = self._parse_multiplicative()
        while True:
            token = self._peek()
            if token and token.kind == "OP" and token.value in {"+", "-"}:
                op = self._consume().value
                node = ASTNode(
                    "binary", op, left=node, right=self._parse_multiplicative()
                )
            else:
                break
        return node

    def _parse_multiplicative(self) -> ASTNode:
        node = self._parse_unary_numeric()
        while True:
            token = self._peek()
            if token and token.kind == "OP" and token.value in {"*", "/", "%"}:
                op = self._consume().value
                node = ASTNode(
                    "binary", op, left=node, right=self._parse_unary_numeric()
                )
            else:
                break
        return node

    def _parse_unary_numeric(self) -> ASTNode:
        token = self._peek()
        if token and token.kind == "OP" and token.value in {"+", "-"}:
            op = self._consume().value
            return ASTNode("unary", op, right=self._parse_unary_numeric())
        return self._parse_primary()

    def _parse_primary(self) -> ASTNode:
        token = self._peek()
        if token is None:
            raise DSLExpressionError("Unexpected end of expression")

        if self._match("LPAREN"):
            node = self._parse_or()
            if not self._match("RPAREN"):
                raise DSLExpressionError("Expected closing parenthesis")
            return node

        if self._match("LBRACK"):
            items: List[ASTNode] = []
            if not self._match("RBRACK"):
                while True:
                    items.append(self._parse_or())
                    if self._match("RBRACK"):
                        break
                    if not self._match("COMMA"):
                        raise DSLExpressionError("Expected ',' in list literal")
            return ASTNode("list", items)

        token = self._consume()
        if token.kind == "NUMBER":
            if "." in token.value:
                return ASTNode("literal", Decimal(token.value))
            return ASTNode("literal", int(token.value))

        if token.kind == "STRING":
            return ASTNode("literal", self._unquote(token.value))

        if token.kind == "KEYWORD":
            if token.value == "TRUE":
                return ASTNode("literal", True)
            if token.value == "FALSE":
                return ASTNode("literal", False)
            if token.value == "NULL":
                return ASTNode("literal", None)
            raise DSLExpressionError(f"Unexpected keyword {token.value}")

        if token.kind == "IDENT":
            if self._match("LPAREN"):
                args: List[ASTNode] = []
                if not self._match("RPAREN"):
                    while True:
                        args.append(self._parse_or())
                        if self._match("RPAREN"):
                            break
                        if not self._match("COMMA"):
                            raise DSLExpressionError("Expected ',' in function call")
                return ASTNode("call", token.value, args=args)
            return ASTNode("identifier", token.value)

        raise DSLExpressionError(f"Unsupported token {token.value!r}")

    @staticmethod
    def _unquote(value: str) -> str:
        return ast.literal_eval(value)


def _resolve_identifier(context: Dict[str, Any], path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
        if value is None:
            return None
    return value


def _coerce_number(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or value is None:
        raise DSLExpressionError(f"Expected number, got {type(value).__name__}")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise DSLExpressionError(f"Invalid numeric literal {value!r}") from exc
    raise DSLExpressionError(f"Expected number, got {type(value).__name__}")


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise DSLExpressionError(f"Invalid datetime {value!r}") from exc
    raise DSLExpressionError(
        f"Expected datetime-compatible value, got {type(value).__name__}"
    )


class SafeExpressionEngine:
    def __init__(self):
        self._tokenizer = Tokenizer()
        self._functions: Dict[str, Callable[..., Any]] = {
            "now": lambda: datetime.now(timezone.utc),
            "len": lambda x: len(x) if x is not None else 0,
            "lower": lambda x: str(x).lower() if x is not None else "",
            "upper": lambda x: str(x).upper() if x is not None else "",
            "abs": abs,
            "min": min,
            "max": max,
            "contains": lambda a, b: b in a if a is not None else False,
            "overlaps": self._overlaps,
            "days_between": self._days_between,
        }

    @staticmethod
    def _overlaps(left: Iterable[Any], right: Iterable[Any]) -> bool:
        return bool(set(left or []).intersection(set(right or [])))

    @staticmethod
    def _days_between(start: Any, end: Any) -> int:
        start_dt = _to_datetime(start)
        end_dt = _to_datetime(end)
        return abs((end_dt - start_dt).days)

    def evaluate(
        self, expression: str, context: Optional[Dict[str, Any]] = None
    ) -> Any:
        tokens = self._tokenizer.tokenize(expression)
        ast = Parser(tokens).parse()
        return self.evaluate_ast(ast, context or {})

    def evaluate_ast(self, node: ASTNode, context: Dict[str, Any]) -> Any:
        if node.node_type == "literal":
            return node.value

        if node.node_type == "identifier":
            return _resolve_identifier(context, str(node.value))

        if node.node_type == "list":
            return [self.evaluate_ast(item, context) for item in (node.value or [])]

        if node.node_type == "call":
            function = self._functions.get(str(node.value))
            if function is None:
                raise DSLExpressionError(f"Unknown function {node.value!r}")
            args = [self.evaluate_ast(arg, context) for arg in (node.args or [])]
            try:
                return function(*args)
            except TypeError as exc:
                raise DSLExpressionError(
                    f"Invalid arguments for function {node.value!r}"
                ) from exc

        if node.node_type == "unary":
            right = self.evaluate_ast(node.right, context) if node.right else None
            if node.value == "NOT":
                return not bool(right)
            if node.value == "+":
                return _coerce_number(right)
            if node.value == "-":
                return -_coerce_number(right)
            raise DSLExpressionError(f"Unsupported unary operator {node.value!r}")

        if node.node_type == "between":
            if node.left is None or not node.args or len(node.args) != 2:
                raise DSLExpressionError("Invalid BETWEEN expression")
            value = self.evaluate_ast(node.left, context)
            lower = self.evaluate_ast(node.args[0], context)
            upper = self.evaluate_ast(node.args[1], context)
            return lower <= value <= upper

        if node.node_type == "binary":
            left = self.evaluate_ast(node.left, context) if node.left else None
            right = self.evaluate_ast(node.right, context) if node.right else None
            return self._apply_binary_operator(str(node.value), left, right)

        raise DSLExpressionError(f"Unsupported AST node type {node.node_type!r}")

    def _apply_binary_operator(self, operator: str, left: Any, right: Any) -> Any:
        if operator == "AND":
            return bool(left) and bool(right)
        if operator == "OR":
            return bool(left) or bool(right)
        if operator == "==":
            return left == right
        if operator == "!=":
            return left != right
        if operator == ">":
            return left > right
        if operator == "<":
            return left < right
        if operator == ">=":
            return left >= right
        if operator == "<=":
            return left <= right
        if operator == "+":
            if isinstance(left, (int, float, Decimal)) and isinstance(
                right, (int, float, Decimal)
            ):
                return _coerce_number(left) + _coerce_number(right)
            return f"{left or ''}{right or ''}"
        if operator == "-":
            return _coerce_number(left) - _coerce_number(right)
        if operator == "*":
            return _coerce_number(left) * _coerce_number(right)
        if operator == "/":
            denominator = _coerce_number(right)
            if denominator == 0:
                raise DSLExpressionError("Division by zero")
            return _coerce_number(left) / denominator
        if operator == "%":
            denominator = _coerce_number(right)
            if denominator == 0:
                raise DSLExpressionError("Modulo by zero")
            return _coerce_number(left) % denominator
        if operator == "IN":
            return left in (right or [])
        if operator == "NOT_IN":
            return left not in (right or [])
        raise DSLExpressionError(f"Unsupported binary operator {operator!r}")
