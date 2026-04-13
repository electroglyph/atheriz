import os
import ast

TARGETS = [
    ("14.1", "atheriz.objects.base_obj", ["Object"]),
    ("14.2", "atheriz.objects.nodes", ["Node"]),
    ("14.3", "atheriz.objects.base_account", ["Account"]),
    ("14.4", "atheriz.objects.base_channel", ["Channel"]),
    ("14.5", "atheriz.objects.base_script", ["Script"]),
    ("14.6", "atheriz.commands.base_cmd", ["Command"]),
    ("14.7", "atheriz.commands.base_cmdset", ["CmdSet"]),
    ("14.8", "atheriz.inputfuncs", ["InputFuncs"]),
    ("14.9", "atheriz.globals.objects", []),
    ("14.10", "atheriz.globals.map", []),
    ("14.11", "atheriz.globals.time", []),
    ("14.12", "atheriz.utils", []),
    ("14.13", "atheriz.objects.funcparser", []),
    ("14.14", "atheriz.settings", [])
]

def format_args(args_node):
    params = []
    
    # Handle normal args
    for arg in args_node.args:
        params.append(arg.arg)
        
    # Handle kwonlyargs
    for arg in args_node.kwonlyargs:
        params.append(arg.arg)
        
    # Handle *args
    if args_node.vararg:
        params.append(f"*{args_node.vararg.arg}")
        
    # Handle **kwargs
    if args_node.kwarg:
        params.append(f"**{args_node.kwarg.arg}")

    return "(" + ", ".join(params) + ")"

def generate_markdown():
    output = []
    output.append("# 14 API Reference\n")
    output.append("[Table of Contents](./table_of_contents.md)\n")
    output.append("This document provides an auto-generated reference for the public classes, methods, and functions within Atheriz.\n")

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    for section_num, module_name, classes_to_document in TARGETS:
        file_path = os.path.join(base_dir, module_name.replace(".", os.sep) + ".py")
        
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
            continue

        output.append(f"## {section_num} `{module_name}`\n")

        module_doc = ast.get_docstring(tree)
        if module_doc:
            output.append(f"{module_doc}\n")

        # Mapping of class names to their AST nodes
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")]
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)]

        if classes_to_document:
            for cls_name in classes_to_document:
                if cls_name in classes:
                    cls_node = classes[cls_name]
                    output.append(f"### Class: `{cls_name}`\n")
                    
                    cls_doc = ast.get_docstring(cls_node)
                    if cls_doc:
                        output.append(f"{cls_doc}\n")
                    
                    methods = [node for node in cls_node.body if isinstance(node, ast.FunctionDef)]
                    for method in methods:
                        # Exclude any method starting with double underscores
                        if method.name.startswith("__"):
                            continue
                            
                        # Check for @property or @<name>.setter decorators
                        is_property = False
                        is_setter = False
                        for decorator in method.decorator_list:
                            if isinstance(decorator, ast.Name) and decorator.id == "property":
                                is_property = True
                            elif isinstance(decorator, ast.Attribute) and decorator.attr == "setter":
                                is_setter = True
                                
                        sig = format_args(method.args)
                        
                        if is_property:
                            output.append(f"#### `@property def {method.name}{sig}`\n")
                        elif is_setter:
                            output.append(f"#### `@{method.name}.setter def {method.name}{sig}`\n")
                        else:
                            output.append(f"#### `def {method.name}{sig}`\n")
                            
                        method_doc = ast.get_docstring(method)
                        if method_doc:
                            output.append(f"{method_doc}\n")
                        output.append("\n")
        else:
            # Document public functions
            for func in functions:
                sig = format_args(func.args)
                output.append(f"### `def {func.name}{sig}`\n")
                
                func_doc = ast.get_docstring(func)
                if func_doc:
                    output.append(f"{func_doc}\n")
                output.append("\n")
            
            # Document public settings/constants if it's the settings or time module
            if module_name in ["atheriz.settings", "atheriz.globals.time"]:
                for assign in assignments:
                    for target in assign.targets:
                        if isinstance(target, ast.Name) and target.id.isupper() and not target.id.startswith("_"):
                            output.append(f"### `{target.id}`\n")
                            try:
                                val = ast.unparse(assign.value)
                                output.append(f"Default value: `{val}`\n\n")
                            except Exception:
                                pass

    output_path = os.path.join(os.path.dirname(__file__), '14_api_reference.md')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output))
    
    print(f"Successfully generated {output_path}")

if __name__ == "__main__":
    generate_markdown()
