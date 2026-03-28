#!/usr/bin/env python3
import ast
import sys
from typing import Dict, List, Any


class CodeAnalyzer:
    def __init__(self, code: str):
        self.code = code
        self.tree = ast.parse(code)
    
    def analyze_complexity(self) -> Dict[str, int]:
        complexity = {}
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_complexity = self._calculate_complexity(node)
                complexity[node.name] = func_complexity
        return complexity
    
    def _calculate_complexity(self, node: ast.AST) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try)):
                complexity += 1
        return complexity
    
    def find_long_functions(self, threshold: int = 20) -> List[Dict[str, Any]]:
        long_functions = []
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lines = node.end_lineno - node.lineno if node.end_lineno else 0
                if lines > threshold:
                    long_functions.append({
                        'name': node.name,
                        'lines': lines,
                        'start_line': node.lineno
                    })
        return long_functions
    
    def check_naming_conventions(self) -> List[Dict[str, Any]]:
        issues = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                if not node.name.islower() or '_' not in node.name:
                    issues.append({
                        'type': 'function_naming',
                        'name': node.name,
                        'line': node.lineno,
                        'suggestion': 'Use snake_case for function names'
                    })
        return issues


if __name__ == '__main__':
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            code = f.read()
        
        analyzer = CodeAnalyzer(code)
        
        print("Code Complexity Analysis:")
        for func, complexity in analyzer.analyze_complexity().items():
            print(f"  {func}: {complexity}")
        
        print("\nLong Functions:")
        for func in analyzer.find_long_functions():
            print(f"  {func['name']}: {func['lines']} lines (line {func['start_line']})")
        
        print("\nNaming Issues:")
        for issue in analyzer.check_naming_conventions():
            print(f"  {issue['name']} at line {issue['line']}: {issue['suggestion']}")
